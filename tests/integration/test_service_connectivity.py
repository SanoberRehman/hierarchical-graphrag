"""Smoke tests proving the CI service containers (Neo4j + Qdrant) are reachable.

These validate the integration harness itself before later PRs add store logic.
Skipped unless RUN_INTEGRATION=1.
"""

from __future__ import annotations

import pytest

from app.config import Settings

pytestmark = pytest.mark.integration


def test_qdrant_reachable() -> None:
    from qdrant_client import QdrantClient

    settings = Settings()
    client = QdrantClient(url=settings.qdrant_url)
    # Any successful call proves connectivity; list_collections is side-effect free.
    client.get_collections()


def test_neo4j_reachable() -> None:
    from neo4j import GraphDatabase

    settings = Settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            value = session.run("RETURN 1 AS n").single()["n"]
            assert value == 1
    finally:
        driver.close()
