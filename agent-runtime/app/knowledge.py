from __future__ import annotations

from dataclasses import dataclass

from app.planning_context import TravelPlanningContext
from app.schemas import TripPlanRequest


@dataclass(frozen=True)
class KnowledgeHit:
    record_type: str
    title: str
    summary: str
    source: str = "runtime_static_knowledge"
    score: float = 0.0

    def to_prompt_line(self) -> str:
        return f"[{self.record_type}] {self.title}: {self.summary}"


@dataclass(frozen=True)
class KnowledgeRetrievalResult:
    hits: tuple[KnowledgeHit, ...]

    def to_trace_detail(self) -> str:
        types = ",".join(hit.record_type for hit in self.hits[:5]) if self.hits else "none"
        return f"hits={len(self.hits)};types={types}"


class KnowledgeRetriever:
    """Replaceable retrieval adapter.

    The first implementation is deterministic and local. It gives the workflow
    a stable RAG boundary without adding a database or vector dependency yet.
    """

    def retrieve(self, request: TripPlanRequest, context: TravelPlanningContext) -> KnowledgeRetrievalResult:
        candidates = _static_destination_knowledge(request.destination)
        scored = sorted(
            ((_score_hit(hit, context), hit) for hit in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        hits = tuple(hit for score, hit in scored if score > 0)[:5]
        return KnowledgeRetrievalResult(hits=hits)


def _static_destination_knowledge(destination: str) -> tuple[KnowledgeHit, ...]:
    city = destination.strip().lower()
    generic = (
        KnowledgeHit(
            record_type="destination_note",
            title=f"{destination} pacing",
            summary="Keep transit buffers between major stops and avoid packing too many cross-city moves into one day.",
            score=0.2,
        ),
        KnowledgeHit(
            record_type="planning_pattern",
            title="weather-aware routing",
            summary="Put outdoor attractions earlier in the day and keep indoor alternatives for rain or extreme heat.",
            score=0.2,
        ),
    )
    city_notes: dict[str, tuple[KnowledgeHit, ...]] = {
        "chengdu": (
            KnowledgeHit("destination_note", "Chengdu food pacing", "Leave flexible dinner time around food districts and avoid scheduling spicy meals immediately before long transfers.", score=0.7),
            KnowledgeHit("destination_note", "Chengdu culture route", "Pair heritage sites with nearby tea houses or neighborhoods to keep the day walkable.", score=0.7),
        ),
        "shanghai": (
            KnowledgeHit("destination_note", "Shanghai family pacing", "For family trips, alternate museums, riverside walks, and mall-adjacent rest stops.", score=0.7),
        ),
        "hangzhou": (
            KnowledgeHit("destination_note", "Hangzhou lake routing", "Group West Lake-side stops by shore area to reduce repeated transfers.", score=0.7),
        ),
        "beijing": (
            KnowledgeHit("destination_note", "Beijing history route", "Historical routes need ticket and security buffer time; avoid more than two major heritage sites per day.", score=0.7),
        ),
        "xi'an": (
            KnowledgeHit("destination_note", "Xi'an short trip", "For one-day trips, combine one major heritage anchor with a compact food area instead of multiple distant sites.", score=0.7),
        ),
        "guangzhou": (
            KnowledgeHit("destination_note", "Guangzhou food route", "Food-focused plans work best when grouped by district and scheduled with late breakfast or dim sum flexibility.", score=0.7),
        ),
    }
    return (*city_notes.get(city, ()), *generic)


def _score_hit(hit: KnowledgeHit, context: TravelPlanningContext) -> float:
    text = f"{hit.title} {hit.summary}".lower()
    score = hit.score
    for term in (*context.interest_terms, *context.preference_terms, *context.style_tags):
        if term.lower() in text:
            score += 0.2
    return score
