"""Owner-authorized knowledge-file deletion and cleanup tests."""

from __future__ import annotations

from sqlalchemy import select

from app.models.document import Document, DocumentChunk, MemoryCategory
from app.models.user import UserRole
from tests.conftest import auth_header


def _upload(client, token: str, title: str = "Delete me") -> dict:
    response = client.post(
        "/api/documents/text",
        headers=auth_header(token),
        json={"title": title, "text": "A uniquely deletable knowledge statement."},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_owner_delete_removes_document_chunks_and_retrieval(
    client, make_user, token_for, db
):
    make_user("delete-owner@example.com", department_name="Finance")
    token = token_for("delete-owner@example.com")
    uploaded = _upload(client, token)

    assert db.get(Document, uploaded["id"]) is not None
    assert db.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == uploaded["id"])
    ).all()

    response = client.delete(
        f"/api/documents/{uploaded['id']}", headers=auth_header(token)
    )

    assert response.status_code == 204
    assert response.content == b""
    assert db.get(Document, uploaded["id"]) is None
    assert db.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == uploaded["id"])
    ).all() == []
    owned = client.get("/api/documents?view=mine", headers=auth_header(token)).json()
    assert uploaded["id"] not in {item["id"] for item in owned}

    answer = client.post(
        "/api/rag/query",
        headers=auth_header(token),
        json={"question": "What is the uniquely deletable knowledge statement?"},
    ).json()
    assert uploaded["id"] not in answer["documents_used"]
    assert all(citation["document_id"] != uploaded["id"] for citation in answer["citations"])


def test_peer_and_admin_cannot_delete_another_users_file(
    client, make_user, token_for, db
):
    make_user("delete-owner2@example.com", department_name="Finance")
    make_user("delete-peer@example.com", department_name="Finance")
    make_user(
        "delete-admin@example.com",
        role=UserRole.admin,
        department_name="Administration",
    )
    uploaded = _upload(client, token_for("delete-owner2@example.com"))

    for email in ("delete-peer@example.com", "delete-admin@example.com"):
        response = client.delete(
            f"/api/documents/{uploaded['id']}",
            headers=auth_header(token_for(email)),
        )
        assert response.status_code == 403
        assert db.get(Document, uploaded["id"]) is not None


def test_owner_can_delete_a_department_shared_file(
    client, make_user, token_for
):
    make_user("shared-delete-owner@example.com", department_name="Finance")
    make_user("shared-delete-peer@example.com", department_name="Finance")
    owner_token = token_for("shared-delete-owner@example.com")
    peer_token = token_for("shared-delete-peer@example.com")
    uploaded = _upload(client, owner_token, "Shared deletion")
    shared = client.patch(
        f"/api/documents/{uploaded['id']}/visibility",
        headers=auth_header(owner_token),
        json={"visibility": "DEPARTMENT"},
    )
    assert shared.status_code == 200

    before = client.get("/api/documents?view=shared", headers=auth_header(peer_token)).json()
    assert uploaded["id"] in {item["id"] for item in before}

    deleted = client.delete(
        f"/api/documents/{uploaded['id']}", headers=auth_header(owner_token)
    )
    assert deleted.status_code == 204
    after = client.get("/api/documents?view=shared", headers=auth_header(peer_token)).json()
    assert uploaded["id"] not in {item["id"] for item in after}


def test_document_delete_route_does_not_delete_private_memory(
    client, make_user, token_for
):
    make_user("memory-delete@example.com")
    token = token_for("memory-delete@example.com")
    memory = client.post(
        "/api/memories",
        headers=auth_header(token),
        json={"content": "Remember my selected compressor setting.", "category": MemoryCategory.USER_NOTE.value},
    )
    assert memory.status_code == 201, memory.text
    memory_id = memory.json()["id"]

    response = client.delete(
        f"/api/documents/{memory_id}", headers=auth_header(token)
    )

    assert response.status_code == 404
    memories = client.get("/api/memories", headers=auth_header(token)).json()
    assert memory_id in {item["id"] for item in memories}


def test_vector_delete_failure_preserves_database_rows(
    client, make_user, token_for, db, monkeypatch
):
    make_user("delete-failure@example.com")
    token = token_for("delete-failure@example.com")
    uploaded = _upload(client, token)

    class _FailingStore:
        def delete_document(self, db, document_id):
            raise RuntimeError("vector backend unavailable")

        def upsert(self, db, document_id):
            raise AssertionError("upsert is not needed when deletion never succeeded")

    monkeypatch.setattr(
        "app.services.document_service.get_vector_store",
        lambda: _FailingStore(),
    )
    response = client.delete(
        f"/api/documents/{uploaded['id']}", headers=auth_header(token)
    )

    assert response.status_code == 409
    assert db.get(Document, uploaded["id"]) is not None
    assert db.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == uploaded["id"])
    ).all()
