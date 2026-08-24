"""End-to-end API test through the ASGI app against live Neo4j + Qdrant.

Exercises the real HTTP surface: async ingest + job polling, the SSE chat stream
(event order and content), and both modes of the subgraph endpoint. Skipped
unless RUN_INTEGRATION=1.
"""

from __future__ import annotations

import json
import time

import pytest

pytestmark = pytest.mark.integration

DOC = (
    "Acme Corporation acquired Beta Industries in a landmark deal. Acme Corporation "
    "also partnered with Gamma Ventures. Beta Industries invested in Delta Systems, "
    "a promising startup. Gamma Ventures added Delta Systems to its portfolio."
)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        container = test_client.app.state.container
        container.vector_store.delete_collection()
        container.graph_store.clear()
        try:
            yield test_client
        finally:
            container.vector_store.delete_collection()
            container.graph_store.clear()


def _wait_for_job(client, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/v1/ingest/jobs/{job_id}").json()
        if body["state"] in {"completed", "failed"}:
            return body
        time.sleep(0.3)
    raise AssertionError("ingest job did not finish in time")


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    for line in raw.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = line.split(":", 1)[1].strip()
            events.append((event_name, json.loads(payload)))
    return events


def test_health(client) -> None:
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "fake"


def test_ingest_chat_and_subgraph_flow(client) -> None:
    # --- async ingest ---
    resp = client.post("/api/v1/ingest", json={"documents": [{"text": DOC, "title": "Acme"}]})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    job = _wait_for_job(client, job_id)
    assert job["state"] == "completed"
    assert job["children_indexed"] >= 1
    assert job["entities_upserted"] >= 3
    assert job["relationships_upserted"] >= 1

    # --- chat over SSE ---
    with client.stream(
        "POST", "/api/v1/chat", json={"query": "What did Acme Corporation acquire?"}
    ) as stream:
        assert stream.status_code == 200
        raw = "".join(stream.iter_text())
    events = _parse_sse(raw)
    types = [name for name, _ in events]

    assert types[0] == "metadata"
    assert "citations" in types
    assert "graph" in types
    assert "token" in types
    assert types[-1] == "done"

    metadata = next(data for name, data in events if name == "metadata")
    query_id = metadata["query_id"]

    citations = next(data for name, data in events if name == "citations")["citations"]
    assert citations and all("text" in c for c in citations)

    graph = next(data for name, data in events if name == "graph")
    assert graph["subgraph"]["nodes"]

    # --- query-specific subgraph endpoint ---
    by_query = client.get("/api/v1/graph/subgraph", params={"query_id": query_id}).json()
    assert by_query["query_id"] == query_id
    assert by_query["subgraph"]["nodes"]

    # --- whole-graph sample ---
    sample = client.get("/api/v1/graph/subgraph").json()
    assert sample["subgraph"]["nodes"]


def test_subgraph_unknown_query_id_returns_404(client) -> None:
    resp = client.get("/api/v1/graph/subgraph", params={"query_id": "does-not-exist"})
    assert resp.status_code == 404
