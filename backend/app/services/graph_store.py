"""Neo4j knowledge-graph store.

Schema:

* Nodes are ``(:Entity {key, name, type, description, parent_chunk_ids,
  child_chunk_ids})`` — ``key`` (``TYPE:lowercased-name``) is the unique identity.
* Edges use the **real, typed relationship type** (e.g. ``[:ACQUIRED]``) rather
  than a generic edge with a type property, for a clean, queryable graph model.
  Types are safe to interpolate because the extraction models sanitize them to
  ``^[A-Z0-9_]+$``.

Provenance arrays (``parent_chunk_ids`` / ``child_chunk_ids``) are merged as
set-unions on every upsert, so re-ingestion accumulates evidence idempotently.
"""

from __future__ import annotations

import re
from collections import defaultdict

from neo4j import GraphDatabase

from app.config import MAX_GRAPH_HOPS, Settings
from app.models.graph import GraphEdge, GraphNode, Subgraph

_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize_text(text: str) -> str:
    """Lowercase and collapse non-alphanumerics to single spaces (for matching)."""
    return _NON_ALNUM.sub(" ", text.lower()).strip()

_UPSERT_NODES = """
UNWIND $nodes AS n
MERGE (e:Entity {key: n.key})
SET e.name = n.name,
    e.type = n.type,
    e.description = coalesce(n.description, e.description),
    e.parent_chunk_ids =
        [x IN coalesce(e.parent_chunk_ids, []) WHERE NOT x IN n.parent_chunk_ids]
        + n.parent_chunk_ids,
    e.child_chunk_ids =
        [x IN coalesce(e.child_chunk_ids, []) WHERE NOT x IN n.child_chunk_ids]
        + n.child_chunk_ids
"""


def _safe_type(rel_type: str) -> str:
    candidate = rel_type.strip().upper()
    return candidate if _TYPE_RE.match(candidate) else "RELATED_TO"


class GraphStore:
    """Typed wrapper over Neo4j for entity/relationship upsert and traversal."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )

    def close(self) -> None:
        self._driver.close()

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def count_entities(self) -> int:
        with self._driver.session() as session:
            return session.run("MATCH (e:Entity) RETURN count(e) AS n").single()["n"]

    def clear(self) -> None:
        """Delete all nodes and relationships (ops/test reset)."""
        with self._driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def init_schema(self) -> None:
        with self._driver.session() as session:
            session.run(
                "CREATE CONSTRAINT entity_key IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.key IS UNIQUE"
            )

    def upsert_nodes(self, nodes: list[GraphNode]) -> int:
        if not nodes:
            return 0
        payload = [n.model_dump() for n in nodes]
        with self._driver.session() as session:
            session.run(_UPSERT_NODES, nodes=payload)
        return len(nodes)

    def upsert_edges(self, edges: list[GraphEdge]) -> int:
        if not edges:
            return 0
        # Group by (sanitized) type so we can interpolate a single literal type
        # per batched UNWIND query.
        by_type: dict[str, list[dict]] = defaultdict(list)
        for edge in edges:
            by_type[_safe_type(edge.type)].append(edge.model_dump())

        with self._driver.session() as session:
            for rel_type, batch in by_type.items():
                query = (
                    "UNWIND $edges AS r "
                    "MATCH (a:Entity {key: r.source}) "
                    "MATCH (b:Entity {key: r.target}) "
                    f"MERGE (a)-[e:`{rel_type}`]->(b) "
                    "SET e.description = coalesce(r.description, e.description), "
                    "    e.parent_chunk_ids = "
                    "        [x IN coalesce(e.parent_chunk_ids, []) "
                    "         WHERE NOT x IN r.parent_chunk_ids] + r.parent_chunk_ids, "
                    "    e.child_chunk_ids = "
                    "        [x IN coalesce(e.child_chunk_ids, []) "
                    "         WHERE NOT x IN r.child_chunk_ids] + r.child_chunk_ids"
                )
                session.run(query, edges=batch)
        return len(edges)

    def seed_keys_by_child_ids(self, child_ids: list[str]) -> list[str]:
        """Entities whose provenance intersects the given child-chunk ids.

        These are the graph "entry points" for a query: the nodes grounded in the
        same chunks that vector search just matched.
        """
        if not child_ids:
            return []
        query = (
            "MATCH (e:Entity) "
            "WHERE any(c IN e.child_chunk_ids WHERE c IN $child_ids) "
            "RETURN e.key AS key"
        )
        with self._driver.session() as session:
            return [record["key"] for record in session.run(query, child_ids=child_ids)]

    def seed_keys_in_text(self, text: str) -> list[str]:
        """Entities whose canonical name appears in the given text.

        A second seeding signal that complements child-chunk provenance: an entity
        can sit squarely in the retrieved *parent* context even when the specific
        matched child slice — or its exact surface form — didn't line up with the
        entity's stored ``child_chunk_ids``. Seeding from the parent text recovers
        those, so graph traversal isn't silently skipped for them.
        """
        if not text or not text.strip():
            return []
        # Whole-token match: normalize the text and space-pad both sides so
        # "Meta" seeds on "Meta" but not on "metaverse".
        padded = f" {_normalize_text(text)} "
        query = (
            "MATCH (e:Entity) "
            "WHERE size(e.name) >= 3 AND $padded CONTAINS (' ' + toLower(e.name) + ' ') "
            "RETURN e.key AS key"
        )
        with self._driver.session() as session:
            return [record["key"] for record in session.run(query, padded=padded)]

    def expand_subgraph(self, seed_keys: list[str], hops: int) -> Subgraph:
        """N-hop neighborhood around the seed entities, as nodes + edges."""
        if not seed_keys:
            return Subgraph()
        hops = max(0, min(int(hops), MAX_GRAPH_HOPS))  # bound traversal depth
        # hops must be a literal in a variable-length pattern; it is an int here.
        query = (
            "MATCH (seed:Entity) WHERE seed.key IN $seed_keys "
            f"OPTIONAL MATCH path = (seed)-[*1..{hops}]-(:Entity) "
            "WITH collect(seed) AS seeds, collect(path) AS paths "
            "WITH seeds + reduce(ns = [], p IN paths | ns + nodes(p)) AS allNodes, "
            "     reduce(rs = [], p IN paths | rs + relationships(p)) AS allRels "
            "UNWIND allNodes AS n "
            "WITH collect(DISTINCT n) AS ns, allRels "
            "RETURN "
            "  [x IN ns | x {.key, .name, .type, .description, "
            "     .parent_chunk_ids, .child_chunk_ids}] AS nodes, "
            "  [r IN allRels | { "
            "     source: startNode(r).key, target: endNode(r).key, "
            "     type: type(r), description: r.description, "
            "     parent_chunk_ids: r.parent_chunk_ids, "
            "     child_chunk_ids: r.child_chunk_ids }] AS rels"
        )
        if hops == 0:
            query = (
                "MATCH (seed:Entity) WHERE seed.key IN $seed_keys "
                "RETURN [x IN collect(seed) | x {.key, .name, .type, .description, "
                "   .parent_chunk_ids, .child_chunk_ids}] AS nodes, [] AS rels"
            )
        with self._driver.session() as session:
            record = session.run(query, seed_keys=seed_keys).single()
        return self._record_to_subgraph(record)

    def sample_subgraph(self, limit: int = 100) -> Subgraph:
        """A bounded sample of the whole graph, for the standalone inspector."""
        query = (
            "MATCH (a:Entity) "
            "OPTIONAL MATCH (a)-[r]->(b:Entity) "
            "WITH a, r, b LIMIT $limit "
            "WITH collect(DISTINCT a) + collect(DISTINCT b) AS ns, collect(r) AS rels "
            "RETURN "
            "  [x IN ns WHERE x IS NOT NULL | x {.key, .name, .type, .description, "
            "     .parent_chunk_ids, .child_chunk_ids}] AS nodes, "
            "  [r IN rels WHERE r IS NOT NULL | { "
            "     source: startNode(r).key, target: endNode(r).key, "
            "     type: type(r), description: r.description, "
            "     parent_chunk_ids: r.parent_chunk_ids, "
            "     child_chunk_ids: r.child_chunk_ids }] AS rels"
        )
        with self._driver.session() as session:
            record = session.run(query, limit=limit).single()
        return self._record_to_subgraph(record)

    @staticmethod
    def _record_to_subgraph(record) -> Subgraph:
        if record is None:
            return Subgraph()
        nodes_by_key: dict[str, GraphNode] = {}
        for n in record["nodes"]:
            if not n:
                continue
            node = GraphNode(**_clean_node(n))
            nodes_by_key.setdefault(node.key, node)
        nodes = list(nodes_by_key.values())
        seen: set[tuple[str, str, str]] = set()
        edges: list[GraphEdge] = []
        for r in record["rels"]:
            if not r:
                continue
            identity = (r["source"], r["target"], r["type"])
            if identity in seen:
                continue
            seen.add(identity)
            edges.append(GraphEdge(**_clean_edge(r)))
        return Subgraph(nodes=nodes, edges=edges)


def _clean_node(raw: dict) -> dict:
    return {
        "key": raw.get("key"),
        "name": raw.get("name"),
        "type": raw.get("type"),
        "description": raw.get("description"),
        "parent_chunk_ids": raw.get("parent_chunk_ids") or [],
        "child_chunk_ids": raw.get("child_chunk_ids") or [],
    }


def _clean_edge(raw: dict) -> dict:
    return {
        "source": raw.get("source"),
        "target": raw.get("target"),
        "type": raw.get("type"),
        "description": raw.get("description"),
        "parent_chunk_ids": raw.get("parent_chunk_ids") or [],
        "child_chunk_ids": raw.get("child_chunk_ids") or [],
    }
