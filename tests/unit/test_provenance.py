"""Unit tests for bidirectional provenance mapping."""

from __future__ import annotations

from app.core.provenance import map_provenance
from app.models.chunk import ChildChunk, ParentChunk
from app.models.graph import Entity, GraphExtraction, Relationship


def _parent_with_children() -> tuple[ParentChunk, list[ChildChunk]]:
    children = [
        ChildChunk(
            id="c0", parent_id="p0", doc_id="d", index=0, token_count=10,
            text="Acme Corp acquired Beta Inc last year.",
        ),
        ChildChunk(
            id="c1", parent_id="p0", doc_id="d", index=1, token_count=10,
            text="Gamma Labs remained independent.",
        ),
    ]
    parent = ParentChunk(
        id="p0", doc_id="d", index=0, token_count=25,
        text="Acme Corp acquired Beta Inc last year. Gamma Labs remained independent.",
        child_ids=["c0", "c1"],
    )
    return parent, children


def test_nodes_carry_bidirectional_provenance() -> None:
    parent, children = _parent_with_children()
    extraction = GraphExtraction(
        entities=[
            Entity(name="Acme Corp", type="COMPANY"),
            Entity(name="Beta Inc", type="COMPANY"),
            Entity(name="Gamma Labs", type="COMPANY"),
        ],
        relationships=[],
    )
    nodes, _ = map_provenance(extraction, parent, children)
    by_name = {n.name: n for n in nodes}

    assert by_name["Acme Corp"].parent_chunk_ids == ["p0"]
    assert by_name["Acme Corp"].child_chunk_ids == ["c0"]
    assert by_name["Gamma Labs"].child_chunk_ids == ["c1"]
    # Node identity key = TYPE:lowercased-name
    assert by_name["Acme Corp"].key == "COMPANY:acme corp"


def test_edges_prefer_child_mentioning_both_endpoints() -> None:
    parent, children = _parent_with_children()
    extraction = GraphExtraction(
        entities=[
            Entity(name="Acme Corp", type="COMPANY"),
            Entity(name="Beta Inc", type="COMPANY"),
        ],
        relationships=[
            Relationship(source="Acme Corp", target="Beta Inc", type="ACQUIRED"),
        ],
    )
    _, edges = map_provenance(extraction, parent, children)
    assert len(edges) == 1
    edge = edges[0]
    assert edge.source == "COMPANY:acme corp"
    assert edge.target == "COMPANY:beta inc"
    assert edge.type == "ACQUIRED"
    assert edge.parent_chunk_ids == ["p0"]
    # c0 mentions both endpoints; c1 mentions neither -> evidence is exactly {c0}
    assert edge.child_chunk_ids == ["c0"]


def test_edge_endpoint_missing_from_entities_gets_synthetic_key() -> None:
    parent, children = _parent_with_children()
    extraction = GraphExtraction(
        entities=[Entity(name="Acme Corp", type="COMPANY")],
        relationships=[
            Relationship(source="Acme Corp", target="Beta Inc", type="ACQUIRED"),
        ],
    )
    _, edges = map_provenance(extraction, parent, children)
    assert edges[0].target == "ENTITY:beta inc"
