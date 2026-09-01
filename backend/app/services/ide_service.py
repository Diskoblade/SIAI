"""OpenHands workspace provisioning through an infrastructure-owned control plane."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ide_code_project import IdeCodeProject
from app.models.ide_workspace import IdeWorkspace
from app.models.user import User
from app.services.authorization_service import department_scope
from app.schemas.ide import IdeCodeFile, IdeCodeProjectUpdate, IdeCodeState


class IdeNotConfiguredError(Exception):
    """Raised when the portal has not been connected to an IDE provisioner."""


class IdeProvisioningError(Exception):
    """Raised when infrastructure cannot create or resolve a user workspace."""


class IdeCodeError(Exception):
    """Raised when saved code state is invalid or cannot be persisted."""


@dataclass(frozen=True)
class ProvisionedWorkspace:
    external_id: str
    status: str
    launch_url: str | None


def is_configured() -> bool:
    return bool(
        settings.openhands_enabled
        and settings.openhands_provisioner_url
        and settings.openhands_provisioner_api_key
        and settings.openhands_public_url
    )


def get_user_workspace(db: Session, user_id: int) -> IdeWorkspace | None:
    return db.scalar(select(IdeWorkspace).where(IdeWorkspace.user_id == user_id))


def get_user_code_project(db: Session, user_id: int) -> IdeCodeProject | None:
    return db.scalar(select(IdeCodeProject).where(IdeCodeProject.user_id == user_id))


def _default_code_state() -> IdeCodeState:
    return IdeCodeState(
        active_file="main.py",
        files=[
            IdeCodeFile(
                path="main.py",
                content=(
                    "def main():\n"
                    "    print('Hello from your saved OpenHands workspace')\n\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                ),
            ),
            IdeCodeFile(
                path="README.md",
                content=(
                    "# Workspace Notes\n\n"
                    "Use this browser editor to keep starter code, snippets, and notes.\n"
                    "Your saved files are tied to your account and reload after login.\n"
                ),
            ),
        ],
    )


def _normalize_file_paths(files: list[IdeCodeFile]) -> list[IdeCodeFile]:
    normalized: list[IdeCodeFile] = []
    seen: set[str] = set()
    for index, file in enumerate(files):
        path = "/".join(part for part in file.path.replace("\\", "/").split("/") if part and part != ".")
        if not path or path.startswith("..") or "/../" in f"/{path}/":
            raise IdeCodeError("Code file paths must be safe relative paths.")
        if path in seen:
            raise IdeCodeError("Each code file path must be unique.")
        if len(file.content) > 100_000:
            raise IdeCodeError("Each code file is limited to 100000 characters.")
        seen.add(path)
        normalized.append(IdeCodeFile(path=path, content=file.content))
    if len(normalized) > 20:
        raise IdeCodeError("The saved code project is limited to 20 files.")
    return normalized


def _state_from_json(value: str | None) -> IdeCodeState:
    if not value:
        return _default_code_state()
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return _default_code_state()
    if not isinstance(data, dict):
        return _default_code_state()
    files = []
    for item in data.get("files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        content = str(item.get("content") or "")
        if path:
            files.append(IdeCodeFile(path=path, content=content))
    try:
        normalized = _normalize_file_paths(files)
    except IdeCodeError:
        return _default_code_state()
    active_file = str(data.get("active_file") or normalized[0].path).strip()
    if active_file not in {file.path for file in normalized}:
        active_file = normalized[0].path
    return IdeCodeState(active_file=active_file, files=normalized)


def _ensure_code_project(db: Session, user: User) -> IdeCodeProject:
    project = get_user_code_project(db, user.id)
    if project is not None:
        return project
    state = _default_code_state()
    project = IdeCodeProject(
        user_id=user.id,
        active_file=state.active_file,
        files_json=state.model_dump_json(),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_or_create_user_code_project(db: Session, user: User) -> IdeCodeProject:
    return _ensure_code_project(db, user)


def get_user_code_state(db: Session, user: User) -> IdeCodeState:
    project = get_user_code_project(db, user.id)
    if project is None:
        return _default_code_state()
    return _state_from_json(project.files_json)


def save_user_code_state(
    db: Session,
    *,
    user: User,
    payload: IdeCodeProjectUpdate,
) -> IdeCodeProject:
    files = _normalize_file_paths(payload.files)
    if not files:
        raise IdeCodeError("Add at least one code file before saving.")
    if payload.active_file not in {file.path for file in files}:
        raise IdeCodeError("The active file must be one of the saved files.")

    project = _ensure_code_project(db, user)
    state = IdeCodeState(active_file=payload.active_file, files=files)
    project.active_file = state.active_file
    project.files_json = state.model_dump_json()
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _workspace_payload(user: User) -> dict:
    scope = department_scope(user.department) if user.department is not None else None
    return {
        "provider": "openhands",
        "workspace_key": f"sih-user-{user.id}",
        "identity": {
            "user_id": str(user.id),
            "department_id": user.department_id,
            "department_scope": scope,
            "role": user.role.value,
        },
    }


def _validate_launch_url(value: object, *, allow_query: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IdeProvisioningError("The provisioner did not return a launch URL.")

    launch = urlparse(value.strip())
    public = urlparse(settings.openhands_public_url.strip())
    if launch.scheme not in {"http", "https"} or not launch.netloc:
        raise IdeProvisioningError("The provisioner returned an invalid launch URL.")
    if (launch.scheme, launch.netloc) != (public.scheme, public.netloc):
        raise IdeProvisioningError("The provisioner returned an unapproved launch origin.")
    if launch.username or launch.password or launch.fragment or (launch.query and not allow_query):
        raise IdeProvisioningError("OpenHands launch URLs must not contain credentials or tokens.")
    return value.strip()


def _parse_provisioner_response(data: object) -> ProvisionedWorkspace:
    if not isinstance(data, dict):
        raise IdeProvisioningError("The provisioner returned an invalid response.")
    external_id = data.get("workspace_id")
    status_value = data.get("status")
    if not isinstance(external_id, str) or not external_id.strip():
        raise IdeProvisioningError("The provisioner did not return a workspace ID.")
    if status_value not in {"provisioning", "ready"}:
        raise IdeProvisioningError("The provisioner returned an unsupported workspace status.")
    launch_url = data.get("launch_url")
    if status_value == "ready":
        launch_url = _validate_launch_url(launch_url)
    elif launch_url is not None:
        launch_url = _validate_launch_url(launch_url)
    return ProvisionedWorkspace(
        external_id=external_id.strip(),
        status=status_value,
        launch_url=launch_url,
    )


def _request_workspace(user: User) -> ProvisionedWorkspace:
    endpoint = f"{settings.openhands_provisioner_url.rstrip('/')}/v1/workspaces"
    headers = {
        "Authorization": f"Bearer {settings.openhands_provisioner_api_key}",
        "Idempotency-Key": f"openhands-user-{user.id}",
    }
    try:
        with httpx.Client(timeout=settings.openhands_request_timeout_seconds) as client:
            response = client.post(endpoint, headers=headers, json=_workspace_payload(user))
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise IdeProvisioningError("The OpenHands workspace service is unavailable.") from exc
    return _parse_provisioner_response(data)


def request_launch_url(user: User, workspace: IdeWorkspace) -> str:
    """Mint a short-lived, non-persisted launch handoff for this exact user."""
    if workspace.user_id != user.id or workspace.status != "ready":
        raise IdeProvisioningError("The OpenHands workspace is not ready.")
    external_id = quote(workspace.external_id, safe="")
    endpoint = f"{settings.openhands_provisioner_url.rstrip('/')}/v1/workspaces/{external_id}/launch"
    headers = {"Authorization": f"Bearer {settings.openhands_provisioner_api_key}"}
    try:
        with httpx.Client(timeout=settings.openhands_request_timeout_seconds) as client:
            response = client.post(endpoint, headers=headers, json={"identity": _workspace_payload(user)["identity"]})
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise IdeProvisioningError("The OpenHands launch service is unavailable.") from exc
    if not isinstance(data, dict):
        raise IdeProvisioningError("The launch service returned an invalid response.")
    return _validate_launch_url(data.get("launch_url"), allow_query=True)


def provision_user_workspace(db: Session, user: User) -> IdeWorkspace:
    if not is_configured():
        raise IdeNotConfiguredError("OpenHands is not configured for this portal.")

    existing = get_user_workspace(db, user.id)
    if existing is not None and existing.status == "ready" and existing.launch_url:
        return existing

    provisioned = _request_workspace(user)
    collision = db.scalar(
        select(IdeWorkspace).where(
            IdeWorkspace.external_id == provisioned.external_id,
            IdeWorkspace.user_id != user.id,
        )
    )
    if collision is not None:
        raise IdeProvisioningError("The provisioner returned a workspace assigned to another user.")
    workspace = existing or IdeWorkspace(
        user_id=user.id,
        external_id=provisioned.external_id,
    )
    workspace.provider = "openhands"
    workspace.external_id = provisioned.external_id
    workspace.status = provisioned.status
    workspace.launch_url = provisioned.launch_url
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace
