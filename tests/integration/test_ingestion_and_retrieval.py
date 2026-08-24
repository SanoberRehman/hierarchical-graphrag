"""End-to-end integration test: ingest → vector search → graph traversal.

Runs the full pipeline with the deterministic fake providers against live Neo4j
and Qdrant (CI service containers). This is the project's primary end-to-end
verification. Skipped unless RUN_INTEGRATION=1.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.models.schemas import DocumentInput, JobState, JobStatus
from app.services.embeddings import FakeEmbeddingProvider
from app.services.graph_store import GraphStore
from app.services.ingestion import IngestionPipeline
from app.services.llm import FakeLLMProvider
from app.services.vector_store import VectorStore

pytestmark = pytest.mark.integration

DOC = """
Acme Corporation acquired Beta Industries in a landmark deal. Acme Corporation
also partnered with Gamma Ventures to expand into new markets. Beta Industries
had previously invested in Delta Systems, a promising technology startup.
Gamma Ventures announced that Delta Systems would join its portfolio. Acme
Corporation continued to grow, and Beta Industries remained a key subsidiary.
Delta Systems built products used by Gamma Ventures and Acme Corporation alike.
""".strip()


@pytest.fixture
def stores():
    settings = Settings(
        llm_provider="fake",
        embedding_provider="fake",
        embedding_dim=128,
        qdrant_collection="test_child_chunks",
        parent_chunk_tokens=120,
        child_chunk_tokens=40,
        parent_chunk_overlap_tokens=0,
        child_chunk_overlap_tokens=10,
    )
    embeddings = FakeEmbeddingProvider(dim=settings.embedding_dim)
    llm = FakeLLMProvider()
    vector_store = VectorStore(settings, embeddings)
    graph_store = GraphStore(settings)

    # Clean slate for deterministic assertions.
    vector_store.delete_collection()
    graph_store.clear()

    pipeline = IngestionPipeline(settings, embeddings, llm, vector_store, graph_store)
    try:
        yield settings, vector_store, graph_store, pipeline
    finally:
        vector_store.delete_collection()
        graph_store.clear()
        vector_store.close()
        graph_store.close()


def test_full_ingest_then_vector_and_graph_retrieval(stores) -> None:
    settings, vector_store, graph_store, pipeline = stores

    status = JobStatus(job_id="job-1", state=JobState.queued, accepted_documents=1)
    pipeline.run([DocumentInput(text=DOC, title="Acme deals")], status)

    # --- ingestion succeeded and populated both stores ---
    assert status.state == JobState.completed
    assert status.processed_documents == 1
    assert status.parents_indexed >= 1
    assert status.children_indexed >= 1
    assert status.entities_upserted >= 3
    assert status.relationships_upserted >= 1

    # --- vector search: child hit carries expandable parent context ---
    hits = vector_store.search("Acme Corporation acquisition of Beta Industries", top_k=5)
    assert hits
    assert all(h.parent_text for h in hits)
    assert any("Acme" in h.parent_text for h in hits)

    # --- graph seeds from the matched chunks, then N-hop expansion ---
    matched_child_ids = [h.child_id for h in hits]
    seeds = graph_store.seed_keys_by_child_ids(matched_child_ids)
    assert seeds, "matched chunks should ground at least one graph entity"

    subgraph = graph_store.expand_subgraph(seeds, hops=settings.graph_max_hops)
    assert subgraph.nodes
    assert subgraph.edges

    # --- provenance is present and bidirectional on graph elements ---
    assert any(n.parent_chunk_ids and n.child_chunk_ids for n in subgraph.nodes)
    assert all(e.source and e.target for e in subgraph.edges)


def test_sample_subgraph_returns_graph(stores) -> None:
    settings, vector_store, graph_store, pipeline = stores
    status = JobStatus(job_id="job-2", state=JobState.queued, accepted_documents=1)
    pipeline.run([DocumentInput(text=DOC, title="Acme deals")], status)

    sample = graph_store.sample_subgraph(limit=50)
    assert sample.nodes


def test_reingest_is_idempotent(stores) -> None:
    settings, vector_store, graph_store, pipeline = stores
    doc = DocumentInput(text=DOC, title="Acme deals", doc_id="fixed-doc")

    s1 = JobStatus(job_id="j1", state=JobState.queued, accepted_documents=1)
    pipeline.run([doc], s1)
    count_after_first = graph_store.count_entities()

    s2 = JobStatus(job_id="j2", state=JobState.queued, accepted_documents=1)
    pipeline.run([doc], s2)
    count_after_second = graph_store.count_entities()

    # Same content re-ingested => nodes merge on key, not duplicate.
    assert count_after_first > 0
    assert count_after_first == count_after_second
