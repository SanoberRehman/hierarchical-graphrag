"""Application configuration, loaded from environment / ``.env``.

All tunables (chunk sizes, provider selection, store URLs, retrieval depth) live
here so the rest of the codebase never reads ``os.environ`` directly. This keeps
the system reproducible and makes the fake-provider offline mode a one-line flip.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["openai", "fake"]

# Hard ceiling on graph-traversal depth. Enforced both at the API (request
# validation) and the store (Cypher clamp) so the two never drift apart.
MAX_GRAPH_HOPS = 4


class Settings(BaseSettings):
    """Strongly-typed settings sourced from environment variables / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Provider selection ---
    llm_provider: Provider = "openai"
    embedding_provider: Provider = "openai"
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # --- Hierarchical chunking ---
    parent_chunk_tokens: int = 1000
    child_chunk_tokens: int = 200
    # Parents are non-overlapping (disjoint) so a piece of source text lives in
    # exactly one parent — keeping parent↔child provenance unambiguous. Recall at
    # boundaries is recovered at the child tier, which does overlap.
    parent_chunk_overlap_tokens: int = 0
    child_chunk_overlap_tokens: int = 30
    tokenizer_encoding: str = "cl100k_base"

    # --- Qdrant (vector store) ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "child_chunks"

    # --- Neo4j (graph store) ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # --- Retrieval tuning ---
    vector_top_k: int = 8
    graph_max_hops: int = 2

    # --- API ---
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow ``CORS_ORIGINS`` to be a comma-separated string in the env."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def uses_openai(self) -> bool:
        return "openai" in (self.llm_provider, self.embedding_provider)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (one per process)."""
    return Settings()
