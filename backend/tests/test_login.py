"""Login endpoint tests covering every account status."""

from __future__ import annotations

from app.models.user import UserStatus


def test_login_success_approved(client, make_user):
    make_user("approved@example.com", status=UserStatus.approved)
    resp = client.post(
        "/api/auth/login",
        json={"email": "approved@example.com", "password": "Password123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "approved@example.com"
    assert body["user"]["department_name"] == "Engineering"
    # Never leak sensitive fields.
    assert "password_hash" not in body["user"]


def test_login_wrong_password(client, make_user):
    make_user("user1@example.com")
    resp = client.post(
        "/api/auth/login",
        json={"email": "user1@example.com", "password": "WrongPassword1"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password."


def test_login_unknown_email(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "Password123"},
    )
    assert resp.status_code == 401
    # Identical message to wrong-password: does not reveal whether email exists.
    assert resp.json()["detail"] == "Invalid email or password."


def test_login_pending(client, make_user):
    make_user("pending@example.com", status=UserStatus.pending)
    resp = client.post(
        "/api/auth/login",
        json={"email": "pending@example.com", "password": "Password123"},
    )
    assert resp.status_code == 403
    assert "awaiting administrator approval" in resp.json()["detail"].lower()


def test_login_rejected(client, make_user):
    make_user("rejected@example.com", status=UserStatus.rejected)
    resp = client.post(
        "/api/auth/login",
        json={"email": "rejected@example.com", "password": "Password123"},
    )
    assert resp.status_code == 403
    assert "has not been approved" in resp.json()["detail"].lower()


def test_login_disabled(client, make_user):
    make_user("disabled@example.com", status=UserStatus.disabled)
    resp = client.post(
        "/api/auth/login",
        json={"email": "disabled@example.com", "password": "Password123"},
    )
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()
