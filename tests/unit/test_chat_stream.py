"""CI-runnable end-to-end test of the /chat SSE streaming contract.

Unlike ``tests/integration/test_api.py`` (which needs live Neo4j + Qdrant), this
exercises the chat route's streaming logic — event order, SSE framing, and the
error path — with a stubbed retriever and the deterministic fake LLM, so it runs
in plain ``pytest -m "not integration"`` with no infrastructure.

The FastAPI ``get_container`` dependency is overridden, so the app's lifespan
(which would connect to the stores) is never started.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.container import get_container
from app.main import create_app
from app.models.graph import GraphEdge, GraphNode, Subgraph
from app.models.retrieval import RetrievalResult
from app.models.schemas import Citation, GraphTriple
from app.services.llm import FakeLLMProvider


def _sample_result(query_id: str) -> RetrievalResult:
    return RetrievalResult(
        query_id=query_id,
        citations=[
            Citation(
                parent_id="p1",
                doc_id="d1",
                title="Company Deals",
                text="Acme Corporation acquired Beta Industries.",
                score=0.91,
                matched_child_ids=["c1"],
            )
        ],
        subgraph=Subgraph(
            nodes=[
                GraphNode(key="COMPANY:acme corporation", name="Acme Corporation", type="COMPANY"),
                GraphNode(key="COMPANY:beta industries", name="Beta Industries", type="COMPANY"),
            ],
            edges=[
                GraphEdge(
                    source="COMPANY:acme corporation",
                    target="COMPANY:beta industries",
                    type="ACQUIRED",
                )
            ],
        ),
        triples=[GraphTriple(source="Acme Corporation", type="ACQUIRED", target="Beta Industries")],
        seed_keys=["COMPANY:acme corporation"],
        context="[1] Acme Corporation acquired Beta Industries.",
    )


class _StubRetriever:
    def __init__(self, result: RetrievalResult | None = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc

    def retrieve(self, query: str, query_id: str, top_k=None, max_hops=None) -> RetrievalResult:
        if self._exc is not None:
            raise self._exc
        assert self._result is not None
        return self._result


def _client(retriever: _StubRetriever):
    from fastapi.testclient import TestClient

    container = SimpleNamespace(
        retriever=retriever,
        llm=FakeLLMProvider(),
        subgraph_cache=SimpleNamespace(put=lambda *a, **k: None),
    )
    app = create_app()
    app.dependency_overrides[get_container] = lambda: container
    # No context manager => lifespan (store connections) is not started.
    return TestClient(app)


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    for line in raw.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            events.append((event_name, json.loads(line.split(":", 1)[1].strip())))
    return events


def test_chat_stream_emits_ordered_events() -> None:
    client = _client(_StubRetriever(result=_sample_result("q-test")))
    with client.stream("POST", "/api/v1/chat", json={"query": "What did Acme acquire?"}) as stream:
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        raw = "".join(stream.iter_text())

    events = _parse_sse(raw)
    types = [name for name, _ in events]

    # Contract: metadata -> citations -> graph -> many token -> done.
    assert types[0] == "metadata"
    assert types[1] == "citations"
    assert types[2] == "graph"
    assert types[-1] == "done"
    assert "token" in types
    # Non-token frames appear exactly once and before any token.
    first_token = types.index("token")
    assert types[:first_token] == ["metadata", "citations", "graph"]

    metadata = next(d for n, d in events if n == "metadata")
    assert metadata["query_id"].startswith("q-")

    citations = next(d for n, d in events if n == "citations")["citations"]
    assert citations and citations[0]["text"]

    graph = next(d for n, d in events if n == "graph")
    assert graph["subgraph"]["nodes"] and graph["triples"]

    answer = "".join(d["text"] for n, d in events if n == "token")
    # The fake LLM extracts entity names from the retrieved context.
    assert "key entities include" in answer
    assert "Acme Corporation" in answer


def test_chat_stream_surfaces_retrieval_error() -> None:
    client = _client(_StubRetriever(exc=RuntimeError("boom in retrieval")))
    with client.stream("POST", "/api/v1/chat", json={"query": "anything"}) as stream:
        assert stream.status_code == 200  # headers already sent before the failure
        raw = "".join(stream.iter_text())

    events = _parse_sse(raw)
    assert events, "expected at least an error event"
    name, data = events[-1]
    assert name == "error"
    assert data["type"] == "error"
    assert "boom in retrieval" in data["message"]


@pytest.mark.parametrize("bad", [{}, {"query": ""}, {"query": "hi", "top_k": 999}])
def test_chat_rejects_invalid_requests(bad: dict) -> None:
    client = _client(_StubRetriever(result=_sample_result("q-test")))
    resp = client.post("/api/v1/chat", json=bad)
    assert resp.status_code == 422
