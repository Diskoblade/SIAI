"""Docker lifecycle operations for isolated OpenHands Agent Canvas containers."""

from __future__ import annotations

import time

import docker
import httpx
from docker.errors import APIError, ImageNotFound, NotFound

from app.config import Settings
from app.database import WorkspaceRecord


class RuntimeError(Exception):
    """Raised when the local Docker runtime cannot create a safe workspace."""


class DockerRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def prepare(self) -> None:
        try:
            self.client.ping()
            try:
                self.client.networks.get(self.settings.docker_network)
            except NotFound:
                self.client.networks.create(
                    self.settings.docker_network,
                    driver="bridge",
                    labels={"sih.openhands.managed": "true"},
                )
        except APIError as exc:
            raise RuntimeError("Docker is unavailable to the OpenHands provisioner") from exc

    def _container(self, workspace: WorkspaceRecord):
        try:
            return self.client.containers.get(workspace.container_name)
        except NotFound:
            return None

    @staticmethod
    def _assert_owned_container(container, workspace: WorkspaceRecord) -> None:
        labels = container.attrs.get("Config", {}).get("Labels", {}) or {}
        if (
            labels.get("sih.openhands.managed") != "true"
            or labels.get("sih.openhands.workspace_id") != workspace.workspace_id
            or labels.get("sih.openhands.user_id") != workspace.user_id
        ):
            raise RuntimeError(
                f"Container name {workspace.container_name!r} is not owned by this workspace"
            )

    def is_ready(self, workspace: WorkspaceRecord) -> bool:
        try:
            container = self._container(workspace)
            if container is None:
                return False
            container.reload()
            self._assert_owned_container(container, workspace)
            if container.status != "running":
                return False
            response = httpx.get(
                f"http://{workspace.container_name}:8000/alive",
                headers={"X-Session-API-Key": workspace.backend_api_key},
                timeout=self.settings.runtime_probe_timeout_seconds,
            )
            return response.status_code < 500
        except (APIError, httpx.HTTPError, RuntimeError):
            return False

    def ensure_workspace(self, workspace: WorkspaceRecord) -> None:
        self.prepare()
        try:
            self.client.images.get(self.settings.openhands_image)
        except ImageNotFound:
            self.client.images.pull(self.settings.openhands_image)
        except APIError as exc:
            raise RuntimeError("Could not inspect the configured OpenHands image") from exc

        state_volume = f"{workspace.container_name}-state"
        projects_volume = f"{workspace.container_name}-projects"
        for volume_name, purpose in (
            (state_volume, "state"),
            (projects_volume, "projects"),
        ):
            try:
                self.client.volumes.get(volume_name)
            except NotFound:
                self.client.volumes.create(
                    name=volume_name,
                    labels={
                        "sih.openhands.managed": "true",
                        "sih.openhands.workspace_id": workspace.workspace_id,
                        "sih.openhands.user_id": workspace.user_id,
                        "sih.openhands.purpose": purpose,
                    },
                )

        container = self._container(workspace)
        if container is None:
            try:
                container = self.client.containers.run(
                    self.settings.openhands_image,
                    name=workspace.container_name,
                    detach=True,
                    network=self.settings.docker_network,
                    environment={
                        "LOCAL_BACKEND_API_KEY": workspace.backend_api_key,
                        "DO_NOT_TRACK": "1",
                        "VITE_DO_NOT_TRACK": "1",
                    },
                    volumes={
                        state_volume: {
                            "bind": "/home/openhands/.openhands",
                            "mode": "rw",
                        },
                        projects_volume: {"bind": "/projects", "mode": "rw"},
                    },
                    labels={
                        "sih.openhands.managed": "true",
                        "sih.openhands.workspace_id": workspace.workspace_id,
                        "sih.openhands.workspace_key": workspace.workspace_key,
                        "sih.openhands.user_id": workspace.user_id,
                    },
                    mem_limit=self.settings.workspace_memory_limit,
                    nano_cpus=int(self.settings.workspace_cpu_limit * 1_000_000_000),
                    pids_limit=self.settings.workspace_pids_limit,
                    security_opt=["no-new-privileges:true"],
                    cap_drop=["ALL"],
                    restart_policy={"Name": "unless-stopped"},
                )
            except APIError as exc:
                raise RuntimeError("Docker could not create the OpenHands container") from exc
        else:
            container.reload()
            self._assert_owned_container(container, workspace)
            if container.status != "running":
                try:
                    container.start()
                except APIError as exc:
                    raise RuntimeError("Docker could not start the OpenHands container") from exc

        deadline = time.monotonic() + self.settings.workspace_startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.is_ready(workspace):
                return
            time.sleep(2)
        raise RuntimeError("OpenHands did not become ready before the startup timeout")

