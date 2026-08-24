"""Unit tests for the deterministic fake providers.

These pin the behaviour the rest of the suite (and CI) relies on: stable,
key-free embeddings whose cosine similarity is meaningful, and an extractor that
reliably produces a connected graph.
"""

from __future__ import annotations

import math

from app.models.graph import GraphExtraction
from app.services.embeddings import FakeEmbeddingProvider
from app.services.llm import FakeLLMProvider


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def test_fake_embeddings_are_deterministic() -> None:
    emb = FakeEmbeddingProvider(dim=128)
    v1 = emb.embed_query("Acme Corp acquired Beta Inc")
    v2 = emb.embed_query("Acme Corp acquired Beta Inc")
    assert v1 == v2
    assert len(v1) == 128


def test_fake_embeddings_are_unit_norm() -> None:
    emb = FakeEmbeddingProvider(dim=64)
    (vec,) = emb.embed_documents(["hello world"])
    assert math.isclose(math.sqrt(sum(v * v for v in vec)), 1.0, rel_tol=1e-6)


def test_fake_embeddings_similarity_tracks_shared_vocabulary() -> None:
    emb = FakeEmbeddingProvider(dim=512)
    query = emb.embed_query("the company acquired a startup in Berlin")
    near = emb.embed_query("a startup in Berlin was acquired by the company")
    far = emb.embed_query("photosynthesis converts sunlight into chemical energy")
    assert _cosine(query, near) > _cosine(query, far)


def test_fake_embeddings_handle_empty_batch() -> None:
    emb = FakeEmbeddingProvider(dim=32)
    assert emb.embed_documents([]) == []


def test_fake_llm_extracts_connected_graph() -> None:
    llm = FakeLLMProvider()
    result = llm.extract_graph(
        "Acme Corp acquired Beta Inc. Later Acme Corp partnered with Gamma Labs."
    )
    assert isinstance(result, GraphExtraction)
    names = {e.name for e in result.entities}
    assert {"Acme Corp", "Beta Inc", "Gamma Labs"} <= names
    assert len(result.relationships) >= 1
    # endpoints of every relationship exist as entities
    for rel in result.relationships:
        assert rel.source in names and rel.target in names


def test_fake_llm_extraction_is_densely_connected() -> None:
    # Windowed linking (not a single chain) so a large corpus renders as a web.
    llm = FakeLLMProvider()
    result = llm.extract_graph(
        "Alpha Corp met Beta Corp and Gamma Corp and Delta Corp and Epsilon Corp."
    )
    names = [e.name for e in result.entities]
    assert len(names) >= 5
    first_out = {r.target for r in result.relationships if r.source == names[0]}
    assert len(first_out) >= 2  # the first entity fans out to several neighbours


def test_fake_llm_stream_is_nonempty_and_joinable() -> None:
    llm = FakeLLMProvider()
    tokens = list(llm.stream_generate("system", "user"))
    assert tokens
    assert "".join(tokens).strip()
