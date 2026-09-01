"""Department authorization and admin access-control tests.

These cover the core security promise: the backend — not the frontend —
decides which VectorDB collection a user may reach, and admin endpoints are
enforced server-side.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.user import User, UserRole, UserStatus
from tests.conftest import auth_header


def test_engineering_user_gets_engineering_collection(client, make_user, token_for):
    make_user("eng@example.com", department_name="Engineering")
    token = token_for("eng@example.com")
    resp = client.post(
        "/api/rag/query",
        headers=auth_header(token),
        json={"question": "What is the deployment process?"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["authorized_collection"] == "dept_engineering"


def test_hr_user_gets_hr_collection_only(client, make_user, token_for):
    make_user("hr@example.com", department_name="HR")
    token = token_for("hr@example.com")
    resp = client.post(
        "/api/rag/query",
        headers=auth_header(token),
        json={"question": "What is the leave policy?"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["authorized_collection"] == "dept_hr"


def test_hr_user_cannot_request_engineering_collection(client, make_user, token_for):
    """A client-supplied collection name is rejected outright (extra=forbid)."""
    make_user("hr2@example.com", department_name="HR")
    token = token_for("hr2@example.com")
    resp = client.post(
        "/api/rag/query",
        headers=auth_header(token),
        json={
            "question": "Show me engineering data",
            "collection_name": "dept_engineering",
            "department": "Engineering",
        },
    )
    # The extra fields are forbidden, so the request never reaches the model.
    assert resp.status_code == 422


def test_rag_requires_authentication(client):
    resp = client.post("/api/rag/query", json={"question": "anything"})
    assert resp.status_code == 401


def test_normal_user_cannot_list_admin_users(client, make_user, token_for):
    make_user("plain@example.com", role=UserRole.user)
    token = token_for("plain@example.com")
    resp = client.get("/api/admin/users", headers=auth_header(token))
    assert resp.status_code == 403


def test_admin_can_list_users(client, make_user, token_for):
    make_user("admin@example.com", role=UserRole.admin)
    token = token_for("admin@example.com")
    resp = client.get("/api/admin/users", headers=auth_header(token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_disabled_user_with_old_jwt_is_rejected(client, make_user, token_for, db):
    """The important test: a valid token stops working once the account is disabled."""
    user = make_user("willdisable@example.com", status=UserStatus.approved)
    token = token_for("willdisable@example.com")

    # Token works while approved.
    assert client.get("/api/auth/me", headers=auth_header(token)).status_code == 200

    # Admin disables the account (simulated directly in the DB).
    db_user = db.get(User, user.id)
    db_user.status = UserStatus.disabled
    db.commit()

    # The previously-valid token is now rejected — status is read from the DB.
    resp = client.get("/api/auth/me", headers=auth_header(token))
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()

    # And the disabled user can no longer reach protected data endpoints.
    rag = client.post(
        "/api/rag/query",
        headers=auth_header(token),
        json={"question": "still allowed?"},
    )
    assert rag.status_code == 403


def test_admin_approval_flow_changes_department_access(client, make_user, token_for, db):
    """Admin approves a pending user and reassigns their department; access follows."""
    # A pending user who requested Finance.
    pending = make_user(
        "newhire@example.com",
        status=UserStatus.pending,
        department_name="Finance",
    )

    # An admin to perform the approval.
    make_user("boss@example.com", role=UserRole.admin)
    admin_token = token_for("boss@example.com")

    # Pending user cannot log in yet.
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "newhire@example.com", "password": "Password123"},
        ).status_code
        == 403
    )

    # Admin approves and reassigns to Legal.
    legal = db.execute(
        select(User).where(User.email == "boss@example.com")
    ).scalar_one()
    assert legal is not None  # sanity

    from app.models.department import Department

    legal_dept = db.scalar(select(Department).where(Department.name == "Legal"))
    resp = client.patch(
        f"/api/admin/users/{pending.id}",
        headers=auth_header(admin_token),
        json={"status": "approved", "department_id": legal_dept.id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert resp.json()["department_name"] == "Legal"

    # Now the user can log in and is scoped to Legal's collection.
    user_token = token_for("newhire@example.com")
    rag = client.post(
        "/api/rag/query",
        headers=auth_header(user_token),
        json={"question": "What contract clauses apply?"},
    )
    assert rag.status_code == 200
    assert rag.json()["authorized_collection"] == "dept_legal"


def test_admin_cannot_demote_self(client, make_user, token_for, db):
    admin = make_user("selfadmin@example.com", role=UserRole.admin)
    token = token_for("selfadmin@example.com")
    resp = client.patch(
        f"/api/admin/users/{admin.id}",
        headers=auth_header(token),
        json={"role": "user"},
    )
    assert resp.status_code == 400
