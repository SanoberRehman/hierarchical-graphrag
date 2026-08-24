"""Bounded LRU cache mapping a chat query_id to the subgraph used for it.

Lets ``GET /api/v1/graph/subgraph?query_id=...`` return the exact subgraph that
grounded a specific answer (per the frontend "sub-graph context used for the
query response" requirement), independent of the SSE stream.
"""

from __future__ import annotations

from collections import OrderedDict

from app.models.graph import Subgraph


class SubgraphCache:
    def __init__(self, maxsize: int = 256) -> None:
        self._maxsize = maxsize
        self._store: OrderedDict[str, Subgraph] = OrderedDict()

    def put(self, query_id: str, subgraph: Subgraph) -> None:
        self._store[query_id] = subgraph
        self._store.move_to_end(query_id)
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def get(self, query_id: str) -> Subgraph | None:
        subgraph = self._store.get(query_id)
        if subgraph is not None:
            self._store.move_to_end(query_id)
        return subgraph
