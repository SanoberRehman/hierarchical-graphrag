"""Chat endpoint: fused retrieval + streamed generation over SSE.

Event order on the stream:
``metadata`` (query_id) → ``citations`` → ``graph`` → many ``token`` → ``done``
(or ``error``). Clients render citations and the graph inspector immediately,
then paint tokens as they arrive.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections.abc import AsyncIterator, Iterator

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from app.container import Container, get_container
from app.models.schemas import (
    ChatRequest,
    CitationsEvent,
    DoneEvent,
    ErrorEvent,
    GraphEvent,
    MetadataEvent,
    TokenEvent,
)
from app.services.llm import GENERATION_SYSTEM_PROMPT, LLMProvider
from app.services.retrieval import build_generation_prompt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["chat"])

_SENTINEL = object()


def _sse(event) -> dict:
    """Serialize a typed event into an SSE frame (named event + JSON data)."""
    return {"event": event.type.value, "data": event.model_dump_json()}


async def _stream_tokens(llm: LLMProvider, system: str, user: str) -> AsyncIterator[str]:
    """Pump a synchronous token generator without blocking the event loop.

    The provider's ``stream_generate`` is a blocking generator (network I/O for
    OpenAI). We run it in a worker thread and hand tokens to the loop via an
    ``asyncio.Queue`` fed with ``call_soon_threadsafe`` — so the consumer just
    ``await``s the queue and no threadpool worker is tied up per active stream.

    If the client disconnects mid-answer, sse-starlette closes this async
    generator, raising ``GeneratorExit`` at the ``yield``. The ``finally`` sets
    ``stop``, so the worker breaks out of ``stream_generate`` promptly instead of
    leaking a thread (and, on the OpenAI path, continuing to bill tokens) until
    process exit.
    """
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()

    def _emit(item: tuple) -> None:
        try:
            loop.call_soon_threadsafe(q.put_nowait, item)
        except RuntimeError:
            pass  # event loop already closed (shutdown) — nothing to deliver to

    def worker() -> None:
        try:
            gen: Iterator[str] = llm.stream_generate(system, user)
            for token in gen:
                if stop.is_set():
                    break
                _emit(("token", token))
        except Exception as exc:  # surfaced to the stream as an error event
            if not stop.is_set():
                _emit(("error", str(exc)))
        finally:
            _emit(("end", _SENTINEL))

    threading.Thread(target=worker, name="llm-stream", daemon=True).start()

    try:
        while True:
            kind, value = await q.get()
            if kind == "end":
                return
            if kind == "error":
                raise RuntimeError(value)
            yield value
    finally:
        stop.set()  # tell the worker to stop on disconnect/cancel/completion


@router.post("/chat")
async def chat(
    request: ChatRequest, container: Container = Depends(get_container)
) -> EventSourceResponse:
    query_id = "q-" + uuid.uuid4().hex[:12]

    async def event_stream() -> AsyncIterator[dict]:
        try:
            result = await run_in_threadpool(
                container.retriever.retrieve,
                request.query,
                query_id,
                request.top_k,
                request.max_hops,
            )
            container.subgraph_cache.put(query_id, result.subgraph)

            yield _sse(MetadataEvent(query_id=query_id, session_id=request.session_id))
            yield _sse(CitationsEvent(citations=result.citations))
            yield _sse(GraphEvent(subgraph=result.subgraph, triples=result.triples))

            user_prompt = build_generation_prompt(request.query, result.context)
            async for token in _stream_tokens(
                container.llm, GENERATION_SYSTEM_PROMPT, user_prompt
            ):
                yield _sse(TokenEvent(text=token))

            yield _sse(DoneEvent(query_id=query_id))
        except Exception as exc:
            logger.exception("Chat request failed")
            yield _sse(ErrorEvent(message=str(exc)))

    return EventSourceResponse(event_stream())
