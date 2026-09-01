from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("PROVISIONER_API_KEY", "test-control-key-that-is-at-least-32-characters")
os.environ.setdefault("DATABASE_PATH", "/tmp/sih-openhands-provisioner-tests-global.db")
os.environ.setdefault("PUBLIC_URL", "http://localhost:8090")

from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Database, WorkspaceRecord
from app.main import GATEWAY_BACKEND_KEY, _rewrite_query, create_app


class FakeRuntime:
    def __init__(self):
        self.ready: set[str] = set()
        self.ensure_calls: list[str] = []

    def is_ready(self, workspace: WorkspaceRecord) -> bool:
        return workspace.workspace_id in self.ready

    def ensure_workspace(self, workspace: WorkspaceRecord) -> None:
        self.ensure_calls.append(workspace.workspace_id)
        self.ready.add(workspace.workspace_id)


def make_client(tmp_path: Path) -> tuple[TestClient, Database, FakeRuntime, Settings]:
    settings = Settings(
        provisioner_api_key="test-control-key-that-is-at-least-32-characters",
        public_url="http://localhost:8090",
        database_path=str(tmp_path / "provisioner.db"),
    )
    database = Database(settings.database_path)
    runtime = FakeRuntime()
    return TestClient(create_app(settings, database=database, runtime=runtime)), database, runtime, settings


def headers(user_id: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer test-control-key-that-is-at-least-32-characters",
        "Idempotency-Key": f"openhands-user-{user_id}",
    }


def payload(user_id: str, workspace_key: str | None = None) -> dict:
    return {
        "provider": "openhands",
        "workspace_key": workspace_key or f"sih-user-{user_id}",
        "identity": {
            "user_id": user_id,
            "department_id": 3,
            "department_scope": "engineering",
            "role": "user",
        },
    }


def wait_until_ready(client: TestClient, user_id: str, workspace_key: str | None = None) -> dict:
    for _ in range(50):
        response = client.post(
            "/v1/workspaces", headers=headers(user_id), json=payload(user_id, workspace_key)
        )
        assert response.status_code == 200, response.text
        if response.json()["status"] == "ready":
            return response.json()
        time.sleep(0.01)
    raise AssertionError("Fake workspace did not become ready")


def test_control_api_requires_backend_secret(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    assert client.get("/healthz").status_code == 200
    response = client.post(
        "/v1/workspaces",
        headers={"Idempotency-Key": "openhands-user-1"},
        json=payload("1"),
    )
    assert response.status_code == 401


def test_workspaces_are_per_user_and_idempotent(tmp_path):
    client, database, runtime, _ = make_client(tmp_path)

    first = wait_until_ready(client, "1")
    repeated = wait_until_ready(client, "1")
    second = wait_until_ready(client, "2")

    assert first == repeated
    assert first["workspace_id"] != second["workspace_id"]
    assert first["launch_url"] == "http://localhost:8090/canvas"
    assert database.get_workspace_by_user("1").workspace_key == "sih-user-1"
    assert database.get_workspace_by_user("2").workspace_key == "sih-user-2"
    assert runtime.ensure_calls.count(first["workspace_id"]) == 1


def test_workspace_key_and_idempotency_collisions_are_rejected(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    wait_until_ready(client, "1", "shared-key")

    collision = client.post(
        "/v1/workspaces",
        headers=headers("2"),
        json=payload("2", "shared-key"),
    )
    assert collision.status_code == 409

    bad_idempotency = client.post(
        "/v1/workspaces",
        headers=headers("2"),
        json=payload("1", "sih-user-1"),
    )
    assert bad_idempotency.status_code == 409


def test_launch_ticket_is_user_bound_single_use_and_not_cached(tmp_path):
    client, database, _, settings = make_client(tmp_path)
    workspace = wait_until_ready(client, "7")

    outsider = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/launch",
        headers={"Authorization": headers("8")["Authorization"]},
        json={"identity": payload("8")["identity"]},
    )
    assert outsider.status_code == 403

    launch = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/launch",
        headers={"Authorization": headers("7")["Authorization"]},
        json={"identity": payload("7")["identity"]},
    )
    assert launch.status_code == 200, launch.text
    assert launch.headers["cache-control"] == "no-store"
    ticket = parse_qs(urlparse(launch.json()["launch_url"]).query)["ticket"][0]

    handoff = client.get(f"/handoff?ticket={ticket}", follow_redirects=False)
    assert handoff.status_code == 303
    assert handoff.headers["location"] == "/canvas"
    assert "HttpOnly" in handoff.headers["set-cookie"]
    assert handoff.headers["cache-control"] == "no-store"
    session_token = handoff.cookies.get(settings.session_cookie_name)
    assert session_token
    assert database.resolve_session(session_token).workspace_id == workspace["workspace_id"]

    replay = client.get(f"/handoff?ticket={ticket}", follow_redirects=False)
    assert replay.status_code == 401


def test_gateway_replaces_only_its_nonsecret_backend_marker():
    query = urlencode_for_test(
        [("session_api_key", GATEWAY_BACKEND_KEY), ("conversation", "abc")]
    )
    rewritten = parse_qs(_rewrite_query(query, "real-secret"))
    assert rewritten == {"session_api_key": ["real-secret"], "conversation": ["abc"]}


def urlencode_for_test(values: list[tuple[str, str]]) -> str:
    from urllib.parse import urlencode

    return urlencode(values)
