"""Unit tests for pure helpers in the store layer (no live services needed)."""

from __future__ import annotations

from app.services.graph_store import _safe_type
from app.services.vector_store import VectorHit, _point_id


def test_point_id_is_deterministic_and_uuid_shaped() -> None:
    a = _point_id("child-123")
    b = _point_id("child-123")
    assert a == b
    assert _point_id("child-999") != a
    assert len(a) == 36 and a.count("-") == 4  # UUID string form


def test_safe_type_passes_valid_and_falls_back_otherwise() -> None:
    assert _safe_type("ACQUIRED") == "ACQUIRED"
    assert _safe_type("works_at") == "WORKS_AT"
    assert _safe_type("2BAD") == "RELATED_TO"  # cannot start with a digit
    assert _safe_type("") == "RELATED_TO"


def test_vector_hit_model() -> None:
    hit = VectorHit(
        child_id="c1", parent_id="p1", doc_id="d1",
        parent_text="parent", child_text="child", score=0.87,
    )
    assert hit.score == 0.87
    assert hit.title is None
