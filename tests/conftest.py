"""Shared pytest fixtures.

Integration tests (marked ``@pytest.mark.integration``) require live Neo4j and
Qdrant. They are skipped unless ``RUN_INTEGRATION=1`` is set — CI sets it after
starting the service containers; locally they stay out of the way.
"""

from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.services.embeddings import FakeEmbeddingProvider
from app.services.llm import FakeLLMProvider


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.getenv("RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_INTEGRATION=1 (needs live Neo4j + Qdrant)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def fake_settings() -> Settings:
    return Settings(
        llm_provider="fake",
        embedding_provider="fake",
        embedding_dim=128,
        parent_chunk_tokens=120,
        child_chunk_tokens=40,
        parent_chunk_overlap_tokens=20,
        child_chunk_overlap_tokens=10,
    )


@pytest.fixture
def fake_embeddings() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(dim=128)


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    return FakeLLMProvider()
