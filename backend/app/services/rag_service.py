"""RAG service — placeholder / integration seam for Qdrant + LLM.

The real implementation will embed the question, search the *authorized*
Qdrant collection, and pass retrieved context to an LLM. For now this returns
a development-mode stub so the full auth + authorization flow can be exercised
end to end. The collection name is always chosen by the backend and passed in
by the route — it is never taken from the client.
"""

from __future__ import annotations

from app.schemas.rag import RagQueryResponse


def answer_question(*, question: str, collection_name: str) -> RagQueryResponse:
    """Return an answer for `question` restricted to `collection_name`.

    TODO (Qdrant/RAG integration):
      1. Embed `question` (e.g. sentence-transformers / an embedding API).
      2. Search ONLY `collection_name` in Qdrant for top-k passages.
      3. Build a prompt from those passages and call the LLM.
      4. Return the answer plus source references.

    Until then, echo back enough to prove the authorization boundary works.
    """
    answer = (
        "RAG is not yet connected. This is a development placeholder. "
        f"Your question would be answered using only the '{collection_name}' "
        "knowledge collection."
    )
    return RagQueryResponse(
        question=question,
        answer=answer,
        authorized_collection=collection_name,
        sources=[],
    )
