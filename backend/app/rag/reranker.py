"""Reranking layer (spec #10).

Reorders the authorized candidate chunks by relevance to the query and keeps
the top-k. Reranking operates ONLY on already-authorized chunks, so it can
never surface unauthorized data.

Providers:
  * LexicalReranker — default, deterministic. Scores by query-term coverage.
  * BGEReranker — local cross-encoder (BAAI/bge-reranker) via FlagEmbedding,
    used when installed and selected.
"""

from __future__ import annotations

from app.core.config import settings
from app.rag.embeddings import tokenize
from app.rag.vector_store import RetrievedChunk

# Minimal stopword list so relevance reflects content words.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "is", "are",
    "what", "which", "how", "do", "does", "this", "that", "with", "by", "be",
    "was", "were", "it", "as", "at", "from", "me", "show", "tell", "please",
    "can", "could", "would", "i", "you", "my", "our", "their", "about",
}


def _content_tokens(text: str) -> set[str]:
    return {t for t in tokenize(text) if len(t) > 2 and t not in _STOPWORDS}


def lexical_relevance(query: str, chunk_text: str) -> float:
    """Fraction of the query's content tokens present in the chunk (0..1)."""
    q = _content_tokens(query)
    if not q:
        return 0.0
    c = _content_tokens(chunk_text)
    return len(q & c) / len(q)


class LexicalReranker:
    def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        for chunk in chunks:
            # Match against the chunk's structural metadata (document title,
            # section, subsection) as well as its body. Headings often carry the
            # topic keyword ("Deployment Process") that the body omits, so
            # including them lets a topical query find the right chunk.
            haystack = " ".join(
                part
                for part in (
                    chunk.document_title,
                    chunk.section,
                    chunk.subsection,
                    chunk.text,
                )
                if part
            )
            # Blend lexical relevance with the retrieval fusion score as a
            # tie-breaker so dense-only matches still rank.
            chunk.score = lexical_relevance(query, haystack) + 0.001 * chunk.score
        ranked = sorted(chunks, key=lambda c: c.score, reverse=True)
        return ranked[:top_k]


class BGEReranker:  # pragma: no cover - requires optional heavy dependency
    def __init__(self) -> None:
        from FlagEmbedding import FlagReranker

        self._model = FlagReranker(settings.bge_reranker_model, use_fp16=False)

    def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        pairs = [[query, c.text] for c in chunks]
        scores = self._model.compute_score(pairs, normalize=True)
        if not isinstance(scores, list):
            scores = [scores]
        for chunk, score in zip(chunks, scores):
            chunk.score = float(score)
        return sorted(chunks, key=lambda c: c.score, reverse=True)[:top_k]


_reranker = None


def get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = BGEReranker() if settings.reranker_provider == "bge" else LexicalReranker()
    return _reranker


def reset_reranker() -> None:
    global _reranker
    _reranker = None
