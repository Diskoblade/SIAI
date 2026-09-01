"""Dense embedding layer — modular so the model can be swapped (spec #6).

Two providers:
  * HashingEmbedder — deterministic, dependency-free bag-of-words hashing into a
    fixed-dim L2-normalized vector. No downloads, no external services; good
    enough to demonstrate dense retrieval and to exercise the security path.
  * OllamaEmbedder — calls a local Ollama server for a real model (bge-m3).

The rest of the app depends only on the `Embedder` protocol, never on a
specific model, so BGE-M3 (via Ollama or a local server) drops in by config.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from app.core.config import settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens — shared by dense hashing and sparse retrieval."""
    return _TOKEN_RE.findall(text.lower())


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...

    def embed_many(self, texts: list[str]) -> list[list[float]]: ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class HashingEmbedder:
    """Feature-hashing embedder. Deterministic and offline."""

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim or settings.embedding_dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in tokenize(text):
            h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[idx] += sign
        return _l2_normalize(vec)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class OllamaEmbedder:
    """Calls a local Ollama server's OpenAI-compatible embeddings API."""

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_embedding_model
        # bge-m3 is 1024-dim; the exact value is discovered on first call.
        self.dim = 1024

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        import httpx  # local import so the default path needs no httpx at import time

        vectors: list[list[float]] = []
        with httpx.Client(timeout=60) as client:
            for text in texts:
                resp = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
                resp.raise_for_status()
                emb = resp.json()["embedding"]
                self.dim = len(emb)
                vectors.append(_l2_normalize(emb))
        return vectors


class OpenAIEmbedder:
    """Hosted embeddings via an OpenAI-compatible /embeddings endpoint.

    Works with OpenAI (text-embedding-3-small), Azure OpenAI, or any compatible
    gateway. No local model is downloaded — ideal when local resources are
    limited. The API key comes from the environment, never from code.
    """

    def __init__(self) -> None:
        self.base_url = settings.embedding_base_url.rstrip("/")
        self.api_key = settings.embedding_api_key
        self.model = settings.embedding_model
        self.dim = 1536  # text-embedding-3-small; refined on first response

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}"}
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": texts},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
        vectors = [_l2_normalize(item["embedding"]) for item in data]
        if vectors:
            self.dim = len(vectors[0])
        return vectors


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Return the configured embedder (cached for the process)."""
    global _embedder
    if _embedder is None:
        provider = settings.embedding_provider
        if provider == "ollama":
            _embedder = OllamaEmbedder()
        elif provider == "openai":
            _embedder = OpenAIEmbedder()
        else:
            _embedder = HashingEmbedder()
    return _embedder


def reset_embedder() -> None:
    """Test helper to clear the cached embedder after a config change."""
    global _embedder
    _embedder = None
