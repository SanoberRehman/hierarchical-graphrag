"""Unit tests for retrieval helpers, the job store, and the subgraph cache."""

from __future__ import annotations

from app.models.graph import GraphEdge, GraphNode, Subgraph
from app.services.cache import SubgraphCache
from app.services.jobs import JobStore
from app.services.retrieval import (
    build_context,
    build_generation_prompt,
    hits_to_citations,
    subgraph_to_triples,
)
from app.services.vector_store import VectorHit


def test_hits_collapse_to_unique_parents_keeping_best_score() -> None:
    def hit(cid: str, pid: str, ptext: str, score: float) -> VectorHit:
        return VectorHit(
            child_id=cid, parent_id=pid, doc_id="d",
            parent_text=ptext, child_text=cid, score=score,
        )

    hits = [hit("c1", "p1", "P1", 0.9), hit("c2", "p1", "P1", 0.5), hit("c3", "p2", "P2", 0.7)]
    citations = hits_to_citations(hits)
    assert [c.parent_id for c in citations] == ["p1", "p2"]  # sorted by score desc
    p1 = next(c for c in citations if c.parent_id == "p1")
    assert p1.score == 0.9
    assert set(p1.matched_child_ids) == {"c1", "c2"}


def test_subgraph_to_triples_uses_node_names() -> None:
    subgraph = Subgraph(
        nodes=[
            GraphNode(key="COMPANY:acme", name="Acme", type="COMPANY"),
            GraphNode(key="COMPANY:beta", name="Beta", type="COMPANY"),
        ],
        edges=[GraphEdge(source="COMPANY:acme", target="COMPANY:beta", type="ACQUIRED")],
    )
    triples = subgraph_to_triples(subgraph)
    assert len(triples) == 1
    assert (triples[0].source, triples[0].type, triples[0].target) == ("Acme", "ACQUIRED", "Beta")


def test_build_context_includes_passages_and_triples() -> None:
    from app.models.schemas import Citation, GraphTriple

    citations = [
        Citation(parent_id="p1", doc_id="d", title="Doc", text="Acme acquired Beta.", score=0.9)
    ]
    triples = [GraphTriple(source="Acme", type="ACQUIRED", target="Beta")]
    context = build_context("q", citations, triples)
    assert "[1]" in context
    assert "Acme acquired Beta." in context
    assert "-[ACQUIRED]->" in context


def test_build_context_handles_empty() -> None:
    assert "No relevant context" in build_context("q", [], [])


def test_generation_prompt_contains_question_and_context() -> None:
    prompt = build_generation_prompt("What did Acme do?", "some context")
    assert "What did Acme do?" in prompt
    assert "some context" in prompt


def test_job_store_lifecycle() -> None:
    store = JobStore()
    status = store.create(accepted_documents=3)
    assert status.accepted_documents == 3
    snapshot = store.get(status.job_id)
    assert snapshot == status  # same data...
    assert snapshot is not status  # ...but a snapshot, isolating concurrent mutation
    assert store.get("nope") is None


def test_subgraph_cache_lru_eviction() -> None:
    cache = SubgraphCache(maxsize=2)
    cache.put("q1", Subgraph())
    cache.put("q2", Subgraph())
    assert cache.get("q1") is not None
    cache.put("q3", Subgraph())  # evicts least-recently-used (q2, since q1 was just read)
    assert cache.get("q2") is None
    assert cache.get("q1") is not None
    assert cache.get("q3") is not None
