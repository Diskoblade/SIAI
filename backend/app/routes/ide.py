"""Authenticated per-user OpenHands coding workspace endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.database import get_db
from app.schemas.ide import (
    IdeCodeProjectUpdate,
    IdeCodeProjectView,
    IdeLaunchResponse,
    IdeStatusResponse,
    IdeWorkspaceView,
)
from app.services import ide_service

router = APIRouter(prefix="/api/ide", tags=["coding workspace"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/status", response_model=IdeStatusResponse)
def ide_status(current_user: CurrentUser, db: DbSession) -> IdeStatusResponse:
    workspace = ide_service.get_user_workspace(db, current_user.id)
    code_project = ide_service.get_user_code_project(db, current_user.id)
    code_state = ide_service.get_user_code_state(db, current_user) if code_project else None
    return IdeStatusResponse(
        enabled=settings.openhands_enabled,
        configured=ide_service.is_configured(),
        workspace=IdeWorkspaceView.model_validate(workspace) if workspace else None,
        code=(
            IdeCodeProjectView(
                id=code_project.id,
                active_file=code_state.active_file,
                files=code_state.files,
                created_at=code_project.created_at,
                updated_at=code_project.updated_at,
            )
            if code_project is not None
            else None
        ),
    )


@router.post(
    "/workspaces",
    response_model=IdeWorkspaceView,
)
def start_workspace(current_user: CurrentUser, db: DbSession) -> IdeWorkspaceView:
    try:
        workspace = ide_service.provision_user_workspace(db, current_user)
    except ide_service.IdeNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ide_service.IdeProvisioningError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return IdeWorkspaceView.model_validate(workspace)


@router.post("/workspaces/launch", response_model=IdeLaunchResponse)
def launch_workspace(
    current_user: CurrentUser,
    db: DbSession,
    response: Response,
) -> IdeLaunchResponse:
    workspace = ide_service.get_user_workspace(db, current_user.id)
    if workspace is None or workspace.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your OpenHands workspace is not ready.",
        )
    try:
        launch_url = ide_service.request_launch_url(current_user, workspace)
    except ide_service.IdeProvisioningError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    response.headers["Cache-Control"] = "no-store"
    return IdeLaunchResponse(launch_url=launch_url)


@router.get("/code", response_model=IdeCodeProjectView)
def get_code_project(current_user: CurrentUser, db: DbSession) -> IdeCodeProjectView:
    project = ide_service.get_user_code_project(db, current_user.id)
    if project is None:
        project = ide_service.get_or_create_user_code_project(db, current_user)
    state = ide_service.get_user_code_state(db, current_user)
    return IdeCodeProjectView(
        id=project.id,
        active_file=state.active_file,
        files=state.files,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.put("/code", response_model=IdeCodeProjectView)
def save_code_project(
    payload: IdeCodeProjectUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> IdeCodeProjectView:
    try:
        project = ide_service.save_user_code_state(db, user=current_user, payload=payload)
    except ide_service.IdeCodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    state = ide_service.get_user_code_state(db, current_user)
    return IdeCodeProjectView(
        id=project.id,
        active_file=state.active_file,
        files=state.files,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
