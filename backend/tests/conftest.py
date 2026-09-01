"""Shared pytest fixtures.

Environment variables are set BEFORE importing the app so configuration (DB
URL, JWT secret) is deterministic. A temporary SQLite file is used and the
schema is rebuilt and reseeded before every test for isolation.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

# --- Must run before any `app.*` import so config picks these up. ---
_TMP_DB = pathlib.Path(tempfile.gettempdir()) / "sih_portal_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["FRONTEND_URL"] = "http://localhost:5173"
os.environ["EMBEDDING_PROVIDER"] = "hashing"
os.environ["VECTOR_STORE"] = "sqlite"
os.environ["RERANKER_PROVIDER"] = "lexical"
os.environ["LLM_PROVIDER"] = "extractive"
os.environ["OPENHANDS_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.department import Department  # noqa: E402
from app.models.user import User, UserRole, UserStatus  # noqa: E402
from app.seed import seed_departments  # noqa: E402

DEFAULT_TEST_PASSWORD = "Password123"


@pytest.fixture(autouse=True)
def _reset_db():
    """Rebuild the schema and reseed departments before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_departments(db)
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def department_id(db):
    """Return the id of a known department (Engineering)."""
    dept = db.scalar(select(Department).where(Department.name == "Engineering"))
    return dept.id


@pytest.fixture
def make_user(db):
    """Factory to insert a user directly with a chosen role/status/department."""

    def _make(
        email: str,
        password: str = DEFAULT_TEST_PASSWORD,
        *,
        full_name: str = "Test User",
        role: UserRole = UserRole.user,
        status: UserStatus = UserStatus.approved,
        department_name: str | None = "Engineering",
    ) -> User:
        department = None
        if department_name is not None:
            department = db.scalar(
                select(Department).where(Department.name == department_name)
            )
        user = User(
            full_name=full_name,
            email=email.lower(),
            password_hash=hash_password(password),
            department_id=department.id if department else None,
            role=role,
            status=status,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def token_for(client):
    """Log in and return a bearer token for the given credentials."""

    def _token(email: str, password: str = DEFAULT_TEST_PASSWORD) -> str:
        resp = client.post("/api/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]

    return _token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
