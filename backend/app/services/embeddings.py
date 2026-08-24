"""Embedding providers behind a single ``EmbeddingProvider`` Protocol.

Two implementations ship:

* :class:`OpenAIEmbeddingProvider` — production, ``text-embedding-3-small``.
* :class:`FakeEmbeddingProvider` — a deterministic, dependency-free hashing
  embedder. It bags words into buckets and L2-normalizes, so texts that share
  vocabulary land close in cosine space. This makes retrieval *assertable* in
  CI without any API key, which is the project's only offline verification path.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.config import Settings

_WORD_RE = re.compile(r"[a-z0-9]+")


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns text into fixed-dimension vectors for the vector store."""

    name: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of documents (child chunks)."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


class FakeEmbeddingProvider:
    """Deterministic hashing embedder — no network, no key, stable across runs."""

    name = "fake"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = _WORD_RE.findall(text.lower())
        for token in tokens:
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dim
            # Sign bit from a second slice keeps the space from collapsing to one orthant.
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        return _l2_normalize(vec)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


class OpenAIEmbeddingProvider:
    """Production embedder backed by the OpenAI embeddings API."""

    name = "openai"

    def __init__(self, api_key: str, model: str, dim: int) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.dim = dim

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(
            model=self._model, input=list(texts), dimensions=self.dim
        )
        return [item.embedding for item in resp.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Factory selecting the embedding provider from settings."""
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set. "
                "Set the key, or use EMBEDDING_PROVIDER=fake for offline mode."
            )
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
            dim=settings.embedding_dim,
        )
    return FakeEmbeddingProvider(dim=settings.embedding_dim)
