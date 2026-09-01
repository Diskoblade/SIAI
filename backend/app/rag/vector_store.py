"""Vector store abstraction with mandatory owner-first authorization filtering.

This is the enforcement point for the platform's highest-priority rule:

    Authenticated user -> resolve trusted context -> apply filter ->
    retrieve authorized chunks ONLY -> (only then) send to the LLM.

The visibility filter is applied as an inseparable part of retrieval. Unauthorized
chunks are never scored, never ranked, and never returned — so they can never
enter the agent state or the model context, regardless of the query, prompt
injection, semantic similarity, or direct id guessing.

Two backends:
  * SqliteVectorStore — default; chunks live in the SQL DB, cosine similarity
    computed in Python, hybrid-fused with a sparse token overlap.
  * QdrantVectorStore — pushes vectors to Qdrant and enforces owner,
    department, and common branches as a server-side payload filter.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import DocumentChunk, Visibility
from app.services.authorization_service import UserContext, can_access_content


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_title: str
    page: int | None
    section: str | None
    subsection: str | None
    text: str
    access_scope: list[str]
    owner_user_id: int | None = None
    department_id: int | None = None
    visibility: str | None = None
    document_type: str = "document"
    memory_category: str | None = None
    dense_score: float = 0.0
    sparse_score: float = 0.0
    score: float = 0.0


def _authorized(chunk: DocumentChunk, context: UserContext) -> bool:
    return can_access_content(
        context=context,
        owner_user_id=chunk.owner_user_id,
        department_id=chunk.department_id,
        visibility=chunk.visibility,
        legacy_access_scope=list(chunk.access_scope or []),
    )


def _cosine(a: list[float], b: list[float]) -> float:
    # Embeddings are L2-normalized, so a dot product is the cosine similarity.
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


def _reciprocal_rank_fusion(
    dense_ranked: list[str], sparse_ranked: list[str], k: int = 60
) -> dict[str, float]:
    """Combine two ranked id lists into fused scores (RRF)."""
    scores: dict[str, float] = {}
    for rank, cid in enumerate(dense_ranked):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    for rank, cid in enumerate(sparse_ranked):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return scores


class SqliteVectorStore:
    """Default local vector store backed by the SQL database."""

    def upsert(self, db: Session, document_id: str) -> None:
        # Chunks are persisted as ORM rows by the ingestion pipeline, so there
        # is nothing extra to push. Present for interface parity with Qdrant.
        return None

    def delete_document(self, db: Session, document_id: str) -> None:
        return None

    def search(
        self,
        db: Session,
        *,
        query_embedding: list[float],
        query_tokens: list[str],
        context: UserContext,
        limit: int,
    ) -> list[RetrievedChunk]:
        qtokens = set(query_tokens)
        dense: list[tuple[str, float]] = []
        sparse: list[tuple[str, float]] = []
        by_id: dict[str, DocumentChunk] = {}

        # Stream chunks; the FIRST thing we do with each row is the scope check.
        # Unauthorized rows are skipped before any scoring — they never become
        # candidates.
        for chunk in db.scalars(select(DocumentChunk)):
            if not _authorized(chunk, context):
                continue
            by_id[chunk.id] = chunk
            dense.append((chunk.id, _cosine(query_embedding, chunk.embedding or [])))
            if qtokens:
                overlap = len(qtokens & set(chunk.tokens or []))
                sparse.append((chunk.id, overlap / len(qtokens)))

        if not by_id:
            return []

        dense_ranked = [cid for cid, s in sorted(dense, key=lambda x: x[1], reverse=True) if s > 0]
        sparse_ranked = [cid for cid, s in sorted(sparse, key=lambda x: x[1], reverse=True) if s > 0]

        fused = _reciprocal_rank_fusion(dense_ranked, sparse_ranked)
        # Fall back to dense order if neither signal fired (e.g. empty query).
        if not fused:
            fused = {cid: s for cid, s in dense}

        dense_map = dict(dense)
        sparse_map = dict(sparse)
        ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:limit]

        results: list[RetrievedChunk] = []
        for cid, fscore in ordered:
            c = by_id[cid]
            results.append(
                RetrievedChunk(
                    chunk_id=c.id,
                    document_id=c.document_id,
                    document_title=c.document_title,
                    page=c.page,
                    section=c.section,
                    subsection=c.subsection,
                    text=c.text,
                    access_scope=list(c.access_scope or []),
                    owner_user_id=c.owner_user_id,
                    department_id=c.department_id,
                    visibility=c.visibility.value if c.visibility else None,
                    document_type=c.document_type,
                    memory_category=c.memory_category,
                    dense_score=dense_map.get(cid, 0.0),
                    sparse_score=sparse_map.get(cid, 0.0),
                    score=fscore,
                )
            )
        return results


class QdrantVectorStore:
    """Qdrant-backed store. Scope enforcement is a server-side payload filter."""

    def __init__(self) -> None:
        from qdrant_client import QdrantClient  # imported only when selected

        self._client = QdrantClient(url=settings.qdrant_url)
        self._collection = settings.qdrant_collection

    def _ensure_collection(self, vector_size: int) -> None:
        """Create the configured collection on the first upload."""
        from qdrant_client.models import Distance, VectorParams

        if self._client.collection_exists(self._collection):
            info = self._client.get_collection(self._collection)
            vectors = info.config.params.vectors
            existing_size = getattr(vectors, "size", None)
            if existing_size is not None and existing_size != vector_size:
                raise RuntimeError(
                    f"Qdrant collection '{self._collection}' uses {existing_size}-dimensional "
                    f"vectors, but the configured embedder produced {vector_size}. "
                    "Use a new collection or re-index all documents."
                )
            return

        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def upsert(self, db: Session, document_id: str) -> None:
        from qdrant_client.models import PointStruct

        chunks = db.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        ).all()
        if not chunks:
            return
        self._ensure_collection(len(chunks[0].embedding))
        points = [
            PointStruct(
                id=c.id,
                vector=c.embedding,
                payload={
                    "chunk_id": c.id,
                    "document_id": c.document_id,
                    "document_title": c.document_title,
                    "department_id": c.department_id,
                    "owner_user_id": c.owner_user_id,
                    "visibility": c.visibility.value if c.visibility else None,
                    "access_scope": list(c.access_scope or []),
                    "document_type": c.document_type,
                    "memory_category": c.memory_category,
                    "page": c.page,
                    "section": c.section,
                    "subsection": c.subsection,
                    "text": c.text,
                },
            )
            for c in chunks
        ]
        self._client.upsert(collection_name=self._collection, points=points, wait=True)

    def delete_document(self, db: Session, document_id: str) -> None:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        if not self._client.collection_exists(self._collection):
            return
        self._client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                )
            ),
            wait=True,
        )

    def search(
        self,
        db: Session,
        *,
        query_embedding: list[float],
        query_tokens: list[str],
        context: UserContext,
        limit: int,
    ) -> list[RetrievedChunk]:
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            IsNullCondition,
            MatchAny,
            MatchValue,
            PayloadField,
        )

        if not self._client.collection_exists(self._collection):
            return []

        private_filter = Filter(
            must=[
                FieldCondition(
                    key="visibility", match=MatchValue(value=Visibility.PRIVATE.value)
                ),
                FieldCondition(
                    key="owner_user_id", match=MatchValue(value=context.user_id)
                ),
            ]
        )
        common_filter = FieldCondition(
            key="visibility", match=MatchValue(value=Visibility.COMMON.value)
        )
        allowed_branches: list = [private_filter, common_filter]
        if context.department_id is not None:
            allowed_branches.append(
                Filter(
                    must=[
                        FieldCondition(
                            key="visibility",
                            match=MatchValue(value=Visibility.DEPARTMENT.value),
                        ),
                        FieldCondition(
                            key="department_id",
                            match=MatchValue(value=context.department_id),
                        ),
                    ]
                )
            )
        if context.allowed_scopes:
            allowed_branches.append(
                Filter(
                    must=[
                        IsNullCondition(is_null=PayloadField(key="visibility")),
                        FieldCondition(
                            key="access_scope",
                            match=MatchAny(any=list(context.allowed_scopes)),
                        ),
                    ]
                )
            )

        # Qdrant evaluates this before returning points. No unauthorized payload
        # can enter reranking or LangGraph state.
        authorization_filter = Filter(should=allowed_branches)
        response = self._client.query_points(
            collection_name=self._collection,
            query=query_embedding,
            query_filter=authorization_filter,
            limit=limit,
            with_payload=True,
        )
        hits = response.points
        results: list[RetrievedChunk] = []
        for h in hits:
            p = h.payload or {}
            results.append(
                RetrievedChunk(
                    chunk_id=str(p.get("chunk_id", h.id)),
                    document_id=p.get("document_id", ""),
                    document_title=p.get("document_title", ""),
                    page=p.get("page"),
                    section=p.get("section"),
                    subsection=p.get("subsection"),
                    text=p.get("text", ""),
                    access_scope=list(p.get("access_scope", [])),
                    owner_user_id=p.get("owner_user_id"),
                    department_id=p.get("department_id"),
                    visibility=p.get("visibility"),
                    document_type=p.get("document_type", "document"),
                    memory_category=p.get("memory_category"),
                    dense_score=float(h.score),
                    score=float(h.score),
                )
            )
        return results


_store = None


def get_vector_store():
    global _store
    if _store is None:
        _store = QdrantVectorStore() if settings.vector_store == "qdrant" else SqliteVectorStore()
    return _store


def reset_vector_store() -> None:
    global _store
    _store = None
