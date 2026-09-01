"""OpenHands per-user provisioning and launch-isolation tests."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.ide_code_project import IdeCodeProject
from app.models.ide_workspace import IdeWorkspace
from app.services import ide_service
from tests.conftest import auth_header


def _configure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openhands_enabled", True)
    monkeypatch.setattr(settings, "openhands_provisioner_url", "https://control.ide.test")
    monkeypatch.setattr(settings, "openhands_provisioner_api_key", "test-control-key")
    monkeypatch.setattr(settings, "openhands_public_url", "https://ide.test")


def test_ide_status_requires_authentication(client):
    assert client.get("/api/ide/status").status_code == 401
    assert client.post("/api/ide/workspaces").status_code == 401


def test_ide_status_reports_disabled_integration(client, make_user, token_for):
    make_user("coder@example.com")
    response = client.get(
        "/api/ide/status", headers=auth_header(token_for("coder@example.com"))
    )
    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "configured": False,
        "provider": "openhands",
        "workspace": None,
        "code": None,
    }


def test_code_project_is_persisted_per_user_and_reloaded_after_login(
    client, make_user, token_for, db
):
    owner = make_user("saved.code@example.com", department_name="Engineering")
    peer = make_user("other.code@example.com", department_name="HR")
    owner_token = token_for("saved.code@example.com")
    other_token = token_for("other.code@example.com")

    loaded = client.get("/api/ide/code", headers=auth_header(owner_token))
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["active_file"] == "main.py"

    saved = client.put(
        "/api/ide/code",
        headers=auth_header(owner_token),
        json={
            "active_file": "src/app.py",
            "files": [
                {"path": "src/app.py", "content": "print('hello')\n"},
                {"path": "README.md", "content": "# Notes\n"},
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["active_file"] == "src/app.py"

    # Simulate logging back in by taking a fresh token and loading the project again.
    refreshed = client.get("/api/ide/code", headers=auth_header(token_for("saved.code@example.com")))
    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()
    assert body["active_file"] == "src/app.py"
    assert {item["path"] for item in body["files"]} == {"src/app.py", "README.md"}

    peer_response = client.get("/api/ide/code", headers=auth_header(other_token))
    assert peer_response.status_code == 200, peer_response.text
    assert peer_response.json()["active_file"] == "main.py"
    assert peer_response.json()["id"] != body["id"]

    records = db.query(IdeCodeProject).all()
    assert {(record.user_id, record.active_file) for record in records} == {
        (owner.id, "src/app.py"),
        (peer.id, "main.py"),
    }


def test_each_user_gets_an_idempotent_isolated_workspace(
    client, make_user, token_for, db, monkeypatch
):
    _configure(monkeypatch)
    first = make_user("first.coder@example.com", department_name="Finance")
    second = make_user("second.coder@example.com", department_name="HR")
    calls: list[int] = []

    def fake_request(user):
        calls.append(user.id)
        return ide_service.ProvisionedWorkspace(
            external_id=f"workspace-{user.id}",
            status="ready",
            launch_url=f"https://ide.test/workspaces/workspace-{user.id}",
        )

    monkeypatch.setattr(ide_service, "_request_workspace", fake_request)
    first_headers = auth_header(token_for("first.coder@example.com"))
    second_headers = auth_header(token_for("second.coder@example.com"))

    first_response = client.post("/api/ide/workspaces", headers=first_headers)
    second_response = client.post("/api/ide/workspaces", headers=second_headers)
    repeated = client.post("/api/ide/workspaces", headers=first_headers)

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    assert repeated.status_code == 200, repeated.text
    assert first_response.json()["external_id"] == f"workspace-{first.id}"
    assert second_response.json()["external_id"] == f"workspace-{second.id}"
    assert "launch_url" not in first_response.json()
    assert calls == [first.id, second.id]

    records = db.query(IdeWorkspace).all()
    assert {(record.user_id, record.external_id) for record in records} == {
        (first.id, f"workspace-{first.id}"),
        (second.id, f"workspace-{second.id}"),
    }


def test_launch_handoff_is_user_bound_and_not_cached(client, make_user, token_for, db, monkeypatch):
    _configure(monkeypatch)
    owner = make_user("workspace.owner@example.com", department_name="Engineering")
    outsider = make_user("workspace.outsider@example.com", department_name="Engineering")
    workspace = IdeWorkspace(
        user_id=owner.id,
        external_id="owner-workspace",
        launch_url="https://ide.test/workspaces/owner-workspace",
        status="ready",
    )
    db.add(workspace)
    db.commit()

    def fake_launch(user, selected_workspace):
        assert user.id == owner.id
        assert selected_workspace.user_id == owner.id
        return "https://ide.test/handoff?ticket=single-use"

    monkeypatch.setattr(ide_service, "request_launch_url", fake_launch)
    owner_response = client.post(
        "/api/ide/workspaces/launch",
        headers=auth_header(token_for("workspace.owner@example.com")),
    )
    assert owner_response.status_code == 200, owner_response.text
    assert owner_response.headers["cache-control"] == "no-store"
    assert owner_response.json()["launch_url"].endswith("ticket=single-use")

    outsider_response = client.post(
        "/api/ide/workspaces/launch",
        headers=auth_header(token_for("workspace.outsider@example.com")),
    )
    assert outsider_response.status_code == 409
    assert outsider.id != owner.id


def test_provisioner_launch_origin_is_restricted(monkeypatch):
    _configure(monkeypatch)
    with pytest.raises(ide_service.IdeProvisioningError, match="unapproved launch origin"):
        ide_service._parse_provisioner_response(
            {
                "workspace_id": "workspace-1",
                "status": "ready",
                "launch_url": "https://attacker.example/workspace-1",
            }
        )
    with pytest.raises(ide_service.IdeProvisioningError, match="credentials or tokens"):
        ide_service._parse_provisioner_response(
            {
                "workspace_id": "workspace-1",
                "status": "ready",
                "launch_url": "https://ide.test/workspace-1?token=stored-secret",
            }
        )


def test_provisioner_cannot_map_two_users_to_one_workspace(
    client, make_user, token_for, monkeypatch
):
    _configure(monkeypatch)
    make_user("collision.one@example.com")
    make_user("collision.two@example.com")

    monkeypatch.setattr(
        ide_service,
        "_request_workspace",
        lambda user: ide_service.ProvisionedWorkspace(
            external_id="shared-workspace",
            status="ready",
            launch_url="https://ide.test/workspaces/shared-workspace",
        ),
    )
    first = client.post(
        "/api/ide/workspaces",
        headers=auth_header(token_for("collision.one@example.com")),
    )
    second = client.post(
        "/api/ide/workspaces",
        headers=auth_header(token_for("collision.two@example.com")),
    )
    assert first.status_code == 200
    assert second.status_code == 502
    assert "another user" in second.json()["detail"]
