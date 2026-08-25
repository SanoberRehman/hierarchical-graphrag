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

# Verb → typed relationship, checked in order (multi-word keys first) against the
# text between two adjacent entities. Lets the offline extractor emit meaningful
# typed edges instead of a uniform RELATED_TO.
_RELATION_KEYWORDS: list[tuple[str, str]] = [
    ("joint venture", "JOINT_VENTURE_WITH"),
    ("acquired a stake", "ACQUIRED_STAKE_IN"),
    ("spun off", "SPUN_OFF"),
    ("licensed technology", "LICENSED_TECHNOLOGY_TO"),
    ("partnered", "PARTNERED_WITH"),
    ("partnership", "PARTNERED_WITH"),
    ("acquired", "ACQUIRED"),
    ("merged", "MERGED_WITH"),
    ("invested", "INVESTED_IN"),
    ("investment", "INVESTED_IN"),
    ("backed", "BACKED"),
    ("founded", "FOUNDED"),
    ("supplies", "SUPPLIES"),
    ("supplier", "SUPPLIES"),
    ("competes", "COMPETES_WITH"),
    ("stake", "ACQUIRED_STAKE_IN"),
    ("licensed", "LICENSED_TECHNOLOGY_TO"),
    ("portfolio", "IN_PORTFOLIO"),
    ("added", "IN_PORTFOLIO"),
]


def _classify_relation(between: str) -> str:
    """Map the text between two adjacent entities to a relationship type."""
    lowered = between.lower()
    for keyword, rel_type in _RELATION_KEYWORDS:
        if keyword in lowered:
            return rel_type
    return "RELATED_TO"


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
        # Entity mentions in text order (with positions, so we can read the verb
        # that sits between two adjacent entities).
        matches: list[tuple[str, int, int]] = []
        for match in _ENTITY_RE.finditer(text):
            phrase = match.group(1).strip(" .,-")
            first = phrase.split()[0] if phrase else ""
            if not phrase or len(phrase) < 3 or first in _STOPWORD_STARTS:
                continue
            matches.append((phrase, match.start(), match.end()))

        seen: dict[str, str] = {}
        ordered: list[str] = []
        for name, _s, _e in matches:
            key = name.lower()
            if key not in seen:
                seen[key] = name
                ordered.append(name)
        entities = [Entity(name=name, type="ENTITY") for name in ordered]

        # Windowed edges keep the graph a connected web (dense enough to look like
        # a real network); the *immediate-next* pair is typed from the verb between
        # them (ACQUIRED, PARTNERED_WITH, ...), farther window pairs fall back to
        # RELATED_TO. So offline extraction is both connected and meaningfully typed.
        relationships: list[Relationship] = []
        edge_seen: set[tuple[str, str]] = set()
        window = 3

        def _add(a: str, b: str, rel_type: str) -> None:
            if a.lower() == b.lower():
                return
            pair = (a.lower(), b.lower())
            if pair in edge_seen:
                return
            edge_seen.add(pair)
            relationships.append(Relationship(source=a, target=b, type=rel_type))

        # Pass 1 — adjacent pairs, typed from the verb between them (claim the
        # pair first so a typed edge is never overwritten by a RELATED_TO one).
        for i in range(len(matches) - 1):
            a, _as, a_end = matches[i]
            b, b_start, _be = matches[i + 1]
            _add(a, b, _classify_relation(text[a_end:b_start]))
        # Pass 2 — farther window pairs as RELATED_TO, for graph density.
        for i in range(len(matches)):
            a = matches[i][0]
            for j in range(i + 2, min(i + 1 + window, len(matches))):
                _add(a, matches[j][0], "RELATED_TO")
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
