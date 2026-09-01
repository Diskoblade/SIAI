"""Dedicated vector-store provider integration tests using Qdrant local mode."""

from qdrant_client import QdrantClient

from sqlalchemy import select

from app.models.department import Department
from app.models.document import Visibility
from app.rag import ingestion
from app.rag.embeddings import get_embedder, tokenize
from app.rag.vector_store import QdrantVectorStore
from app.services.authorization_service import UserContext


def test_qdrant_creates_collection_and_filters_scopes(db):
    finance = ingestion.ingest_text(
        db,
        title="Finance Threshold",
        text="The emergency procurement threshold is 47 lakh rupees.",
        access_scope=["finance"],
        owner_department_id=None,
    )
    hr = ingestion.ingest_text(
        db,
        title="HR Leave",
        text="Employees receive thirty days of annual leave.",
        access_scope=["hr"],
        owner_department_id=None,
    )

    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store._client = QdrantClient(location=":memory:")
    store._collection = "test_documents"
    store.upsert(db, finance.id)
    store.upsert(db, hr.id)

    assert store._client.collection_exists(store._collection)
    query = "What is the emergency procurement threshold?"
    results = store.search(
        db,
        query_embedding=get_embedder().embed(query),
        query_tokens=tokenize(query),
        context=UserContext(
            user_id=100,
            department_id=None,
            department_scope="finance",
            role="user",
            capability="OFFICER",
            allowed_scopes=["finance", "common"],
        ),
        limit=10,
    )
    returned = {result.document_id for result in results}
    assert finance.id in returned
    assert hr.id not in returned


def test_qdrant_enforces_private_department_and_common_visibility(db):
    finance_id = db.scalar(select(Department).where(Department.name == "Finance")).id
    hr_id = db.scalar(select(Department).where(Department.name == "HR")).id
    private = ingestion.ingest_text(
        db,
        title="Private File",
        text="private owner-only vector",
        access_scope=[],
        owner_department_id=finance_id,
        owner_user_id=1,
        visibility=Visibility.PRIVATE,
    )
    department = ingestion.ingest_text(
        db,
        title="Finance Shared",
        text="finance department vector",
        access_scope=["finance"],
        owner_department_id=finance_id,
        owner_user_id=1,
        visibility=Visibility.DEPARTMENT,
    )
    common = ingestion.ingest_text(
        db,
        title="Common Shared",
        text="common organization vector",
        access_scope=["common"],
        owner_department_id=None,
        owner_user_id=1,
        visibility=Visibility.COMMON,
    )

    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store._client = QdrantClient(location=":memory:")
    store._collection = "visibility_documents"
    for document in (private, department, common):
        store.upsert(db, document.id)

    query = "vector"

    def search(context):
        return {
            result.document_id
            for result in store.search(
                db,
                query_embedding=get_embedder().embed(query),
                query_tokens=tokenize(query),
                context=context,
                limit=10,
            )
        }

    owner = UserContext(1, finance_id, "finance", "user", "OFFICER", ["finance", "common"])
    peer = UserContext(2, finance_id, "finance", "user", "OFFICER", ["finance", "common"])
    outsider = UserContext(3, hr_id, "hr", "user", "OFFICER", ["hr", "common"])

    assert search(owner) == {private.id, department.id, common.id}
    assert search(peer) == {department.id, common.id}
    assert search(outsider) == {common.id}


def test_qdrant_delete_document_removes_all_document_points(db):
    finance_id = db.scalar(select(Department).where(Department.name == "Finance")).id
    document = ingestion.ingest_text(
        db,
        title="Disposable vectors",
        text="This vector should be removed from Qdrant.",
        access_scope=[],
        owner_department_id=finance_id,
        owner_user_id=42,
        visibility=Visibility.PRIVATE,
    )
    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store._client = QdrantClient(location=":memory:")
    store._collection = "deletion_documents"
    store.upsert(db, document.id)
    context = UserContext(42, finance_id, "finance", "user", "OFFICER", ["finance", "common"])
    query = "removed Qdrant vector"

    def search():
        return store.search(
            db,
            query_embedding=get_embedder().embed(query),
            query_tokens=tokenize(query),
            context=context,
            limit=10,
        )

    assert {result.document_id for result in search()} == {document.id}
    store.delete_document(db, document.id)
    assert search() == []


def test_qdrant_delete_is_safe_before_collection_exists(db):
    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store._client = QdrantClient(location=":memory:")
    store._collection = "missing_collection"

    store.delete_document(db, "unknown-document")
