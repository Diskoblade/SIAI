"""Signup endpoint tests."""

from __future__ import annotations

from sqlalchemy import select

from app.models.user import User, UserRole, UserStatus


def test_signup_success(client, department_id):
    resp = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Rahul Kumar",
            "email": "rahul@example.com",
            "password": "StrongPassword123",
            "department_id": department_id,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert "waiting for administrator approval" in body["message"].lower()
    # No password data leaks in the response.
    assert "password" not in body
    assert "password_hash" not in body


def test_signup_creates_pending_user_role_user(client, department_id, db):
    client.post(
        "/api/auth/signup",
        json={
            "full_name": "Pending Person",
            "email": "pending@example.com",
            "password": "StrongPassword123",
            "department_id": department_id,
        },
    )
    user = db.scalar(select(User).where(User.email == "pending@example.com"))
    assert user is not None
    assert user.role is UserRole.user
    assert user.status is UserStatus.pending
    # Password is stored only as a hash, never plaintext.
    assert user.password_hash != "StrongPassword123"
    assert user.password_hash.startswith("$argon2")


def test_signup_duplicate_email(client, department_id):
    payload = {
        "full_name": "First",
        "email": "dupe@example.com",
        "password": "StrongPassword123",
        "department_id": department_id,
    }
    assert client.post("/api/auth/signup", json=payload).status_code == 201
    resp = client.post("/api/auth/signup", json={**payload, "full_name": "Second"})
    assert resp.status_code == 409
    assert "already registered" in resp.json()["detail"].lower()


def test_signup_duplicate_email_case_insensitive(client, department_id):
    payload = {
        "full_name": "First",
        "email": "Case@Example.com",
        "password": "StrongPassword123",
        "department_id": department_id,
    }
    assert client.post("/api/auth/signup", json=payload).status_code == 201
    resp = client.post(
        "/api/auth/signup",
        json={**payload, "email": "case@example.com", "full_name": "Second"},
    )
    assert resp.status_code == 409


def test_signup_invalid_email(client, department_id):
    resp = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Bad Email",
            "email": "not-an-email",
            "password": "StrongPassword123",
            "department_id": department_id,
        },
    )
    assert resp.status_code == 422


def test_signup_password_too_short(client, department_id):
    resp = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Short Pw",
            "email": "short@example.com",
            "password": "short",
            "department_id": department_id,
        },
    )
    assert resp.status_code == 422


def test_signup_invalid_department(client):
    resp = client.post(
        "/api/auth/signup",
        json={
            "full_name": "No Dept",
            "email": "nodept@example.com",
            "password": "StrongPassword123",
            "department_id": 99999,
        },
    )
    assert resp.status_code == 400
    assert "invalid department" in resp.json()["detail"].lower()


def test_signup_cannot_self_assign_admin_or_approved(client, department_id, db):
    """Extra fields like role/status must never elevate a signup."""
    resp = client.post(
        "/api/auth/signup",
        json={
            "full_name": "Sneaky",
            "email": "sneaky@example.com",
            "password": "StrongPassword123",
            "department_id": department_id,
            "role": "admin",
            "status": "approved",
        },
    )
    assert resp.status_code == 201
    user = db.scalar(select(User).where(User.email == "sneaky@example.com"))
    assert user.role is UserRole.user
    assert user.status is UserStatus.pending
