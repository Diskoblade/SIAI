"""JWT / protected-endpoint tests."""

from __future__ import annotations

import jwt

from app.core.security import create_access_token
from tests.conftest import auth_header


def test_valid_jwt_grants_me(client, make_user, token_for):
    make_user("valid@example.com")
    token = token_for("valid@example.com")
    resp = client.get("/api/auth/me", headers=auth_header(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "valid@example.com"
    assert body["status"] == "approved"
    assert body["department_name"] == "Engineering"


def test_missing_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_expired_jwt(client, make_user):
    user = make_user("expired@example.com")
    # Token that expired one minute ago.
    token = create_access_token(
        subject=user.id,
        department_id=user.department_id,
        role=user.role.value,
        expires_minutes=-1,
    )
    resp = client.get("/api/auth/me", headers=auth_header(token))
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_invalid_signature(client, make_user):
    user = make_user("badsig@example.com")
    # Forge a token signed with the wrong secret.
    forged = jwt.encode(
        {"sub": str(user.id), "role": "user", "department_id": user.department_id},
        "totally-wrong-secret",
        algorithm="HS256",
    )
    resp = client.get("/api/auth/me", headers=auth_header(forged))
    assert resp.status_code == 401


def test_malformed_token(client):
    resp = client.get("/api/auth/me", headers=auth_header("not.a.jwt"))
    assert resp.status_code == 401
