"""LLM providers behind a single ``LLMProvider`` Protocol.

Responsibilities of an LLM provider:

* :meth:`extract_graph` — structured-output extraction of entities and typed
  relationships from a chunk of text.
* :meth:`stream_generate` — token-streamed answer generation grounded in context.

Two implementations ship:

* :class:`OpenAILLMProvider` — production, using structured outputs + streaming.
* :class:`FakeLLMProvider` — deterministic heuristics (capitalized phrases as
  entities, adjacency as generic ``RELATED_TO`` relationships; a fixed
  placeholder answer). No key required, which lets the whole ingest→graph→chat
  path be exercised in CI.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from typing import Protocol, runtime_checkable

from app.config import Settings
from app.models.graph import Entity, GraphExtraction, Relationship

EXTRACTION_SYSTEM_PROMPT = """\
You are a precise information-extraction engine building a knowledge graph.
From the text, extract:
1. Named entities (nodes) — organizations, people, products, places, technologies, events.
2. Explicit, typed, directed relationships (edges) between those entities, e.g.
   (Company)-[ACQUIRED]->(Startup), (Person)-[FOUNDED]->(Company).

Rules:
- Only extract relationships that are explicitly stated or unambiguously implied by THIS text.
- Use concise SCREAMING_SNAKE_CASE relationship types.
- Use the entity's canonical name; do not invent entities not present in the text.
- Prefer specific types (ACQUIRED, FOUNDED, PARTNERED_WITH) over generic RELATED_TO.
- Every relationship's source and target must appear in the entities list."""

GENERATION_SYSTEM_PROMPT = """\
You are a helpful research assistant answering strictly from the provided context.
The context contains (a) passages retrieved from documents and (b) knowledge-graph
relationship triples. Ground every claim in that context and cite the passages you
use inline as [1], [2], ... matching the numbered context blocks. If the context is
insufficient, say so plainly rather than guessing."""

# Capitalized word runs; the char class excludes '.' so matches stop at sentence
# boundaries ("Beta Inc." -> "Beta Inc", not "Beta Inc. Later ...").
_ENTITY_RE = re.compile(r"\b([A-Z][A-Za-z0-9&\-]*(?:\s+[A-Z][A-Za-z0-9&\-]*)*)\b")
_STOPWORD_STARTS = {
    "The", "A", "An", "This", "That", "These", "Those", "It", "In", "On", "At",
    "For", "And", "But", "Or", "If", "When", "While", "However", "Meanwhile",
    "Later", "Then", "After", "Before", "During", "Its", "Their", "His", "Her",
}
# Prompt/label words that must never be mistaken for entities in the fake
# extractive answer (they appear in the assembled generation prompt).
_PROMPT_BOILERPLATE = {
    "question", "context", "answer", "cite", "retrieved", "passages", "passage",
    "knowledge", "knowledge-graph", "relationships", "relationship", "source",
    "sources", "note", "query", "only",
}


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def extract_graph(self, text: str) -> GraphExtraction:
        """Extract entities and relationships from a single chunk of text."""
        ...

    def stream_generate(self, system: str, user: str) -> Iterator[str]:
        """Yield answer tokens/fragments grounded in the user prompt/context."""
        ...


class FakeLLMProvider:
    """Deterministic, dependency-free stand-in for offline runs and CI."""

    name = "fake"

    def extract_graph(self, text: str) -> GraphExtraction:
        seen: dict[str, str] = {}
        ordered: list[str] = []
        for match in _ENTITY_RE.finditer(text):
            phrase = match.group(1).strip(" .,-")
            first = phrase.split()[0] if phrase else ""
            if not phrase or len(phrase) < 3 or first in _STOPWORD_STARTS:
                continue
            key = phrase.lower()
            if key not in seen:
                seen[key] = phrase
                ordered.append(phrase)

        entities = [Entity(name=name, type="ENTITY") for name in ordered]
        relationships: list[Relationship] = []
        # Link each entity to the next few distinct entities (a sliding window)
        # rather than a single chain, so the offline graph reads as a connected
        # *web* — dense enough that a large corpus renders as a real network.
        window = 3
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 : i + 1 + window]:
                relationships.append(Relationship(source=a, target=b, type="RELATED_TO"))
        return GraphExtraction(entities=entities, relationships=relationships)

    def stream_generate(self, system: str, user: str) -> Iterator[str]:
        # Deterministic, key-free answer. It doesn't reason like an LLM, but it IS
        # grounded: it pulls the actual entity names out of the retrieved context
        # so a zero-key demo surfaces real content instead of a fixed sentence.
        # Genuine, query-specific answers need OPENAI_API_KEY (LLM_PROVIDER=openai).
        # Scan only the retrieved-context portion — not the question/instructions.
        haystack = user.split("Context:", 1)[-1]
        names: list[str] = []
        seen: set[str] = set()
        for match in _ENTITY_RE.finditer(haystack):
            phrase = match.group(1).strip(" .,-")
            first = phrase.split()[0] if phrase else ""
            if (
                not phrase
                or len(phrase) < 3
                or first in _STOPWORD_STARTS
                or first.lower() in _PROMPT_BOILERPLATE
            ):
                continue
            key = phrase.lower()
            if key not in seen:
                seen.add(key)
                names.append(phrase)
            if len(names) >= 5:
                break
        if len(names) >= 2:
            listed = ", ".join(names[:-1]) + f", and {names[-1]}"
        elif names:
            listed = names[0]
        else:
            listed = "the entities in the retrieved passages"
        answer = (
            f"Based on the retrieved context, the key entities include {listed} — "
            "connected through the knowledge-graph relationships shown above [1]. "
            "(Zero-key demo: this is a deterministic extractive summary; set "
            "OPENAI_API_KEY for a full generated answer.)"
        )
        yield from _tokenize_for_stream(answer)


def _tokenize_for_stream(text: str) -> Sequence[str]:
    """Split into whitespace-preserving fragments to mimic token streaming."""
    return re.findall(r"\S+\s*", text)


class OpenAILLMProvider:
    """Production provider: structured outputs for extraction, streaming for chat."""

    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def extract_graph(self, text: str) -> GraphExtraction:
        from openai import OpenAIError

        try:
            completion = self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                response_format=GraphExtraction,
                temperature=0,
            )
        except OpenAIError as exc:  # pragma: no cover - network path
            raise RuntimeError(f"OpenAI extraction failed: {exc}") from exc
        parsed = completion.choices[0].message.parsed
        return parsed or GraphExtraction()

    def stream_generate(self, system: str, user: str) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            stream=True,
        )
        for chunk in stream:  # pragma: no cover - network path
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Factory selecting the LLM provider from settings."""
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
                "Set the key, or use LLM_PROVIDER=fake for offline mode."
            )
        return OpenAILLMProvider(api_key=settings.openai_api_key, model=settings.openai_chat_model)
    return FakeLLMProvider()
