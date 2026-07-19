from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.schemas import TripPlanRequest


TERM_SPLIT_PATTERN = re.compile("[,\uFF0C;\uFF1B\u3001|/]+")


class PromptKnowledgeHit(Protocol):
    def to_prompt_line(self) -> str:
        ...


@dataclass(frozen=True)
class TravelPlanningContext:
    destination: str
    days: int
    budget: str
    date_window: str
    transportation: str
    accommodation: str
    interest_terms: tuple[str, ...]
    preference_terms: tuple[str, ...]
    style_tags: tuple[str, ...]
    constraints_present: bool
    retrieved_knowledge: tuple[PromptKnowledgeHit, ...] = ()

    @property
    def interest_summary(self) -> str:
        return ", ".join(self.interest_terms) if self.interest_terms else "local culture"

    @property
    def preference_summary(self) -> str:
        return ", ".join(self.preference_terms) if self.preference_terms else "not specified"

    def to_prompt_lines(self) -> list[str]:
        return [
            f"Destination: {self.destination}",
            f"Days: {self.days}",
            f"Budget: {self.budget}",
            f"Date window: {self.date_window}",
            f"Transportation: {self.transportation}",
            f"Accommodation: {self.accommodation}",
            f"Interests: {self.interest_summary}",
            f"Preferences: {self.preference_summary}",
            f"Style tags: {', '.join(self.style_tags) if self.style_tags else 'general'}",
            f"Additional constraints present: {'yes' if self.constraints_present else 'no'}",
            *[f"Retrieved knowledge: {hit.to_prompt_line()}" for hit in self.retrieved_knowledge],
        ]

    def to_trace_detail(self) -> str:
        tags = ",".join(self.style_tags[:3]) if self.style_tags else "general"
        return (
            f"days={self.days}; interests={len(self.interest_terms)}; "
            f"preferences={len(self.preference_terms)}; constraints={'yes' if self.constraints_present else 'no'}; "
            f"tags={tags}; knowledge={len(self.retrieved_knowledge)}"
        )

    def with_retrieved_knowledge(self, hits: tuple[PromptKnowledgeHit, ...]) -> "TravelPlanningContext":
        return TravelPlanningContext(
            destination=self.destination,
            days=self.days,
            budget=self.budget,
            date_window=self.date_window,
            transportation=self.transportation,
            accommodation=self.accommodation,
            interest_terms=self.interest_terms,
            preference_terms=self.preference_terms,
            style_tags=self.style_tags,
            constraints_present=self.constraints_present,
            retrieved_knowledge=hits,
        )


@dataclass(frozen=True)
class ResearchContextView:
    destination: str
    days: int
    date_window: str
    budget: str
    interests: tuple[str, ...]
    preferences: tuple[str, ...]
    constraints_present: bool
    knowledge_lines: tuple[str, ...]
    missing_fact_types: tuple[str, ...]

    def to_prompt_lines(self) -> list[str]:
        return [
            f"Research destination: {self.destination}",
            f"Trip length: {self.days} day(s)",
            f"Date window: {self.date_window}",
            f"Budget tier: {self.budget}",
            f"Interests: {', '.join(self.interests) if self.interests else 'local culture'}",
            f"Preferences: {', '.join(self.preferences) if self.preferences else 'not specified'}",
            f"Constraints present: {'yes' if self.constraints_present else 'no'}",
            f"Missing fact types: {', '.join(self.missing_fact_types) if self.missing_fact_types else 'none'}",
            *[f"Knowledge: {line}" for line in self.knowledge_lines],
        ]

    def to_trace_detail(self) -> str:
        return (
            f"research_view;days={self.days};interests={len(self.interests)};"
            f"knowledge={len(self.knowledge_lines)};missing={','.join(self.missing_fact_types) or 'none'}"
        )


@dataclass(frozen=True)
class PlannerContextView:
    destination: str
    days: int
    budget: str
    transportation: str
    accommodation: str
    interests: tuple[str, ...]
    preferences: tuple[str, ...]
    style_tags: tuple[str, ...]
    knowledge_lines: tuple[str, ...]
    quality_focus: tuple[str, ...]

    def to_prompt_lines(self) -> list[str]:
        return [
            f"Planner destination: {self.destination}",
            f"Trip length: {self.days} day(s)",
            f"Budget tier: {self.budget}",
            f"Transportation: {self.transportation}",
            f"Accommodation: {self.accommodation}",
            f"Interests: {', '.join(self.interests) if self.interests else 'local culture'}",
            f"Preferences: {', '.join(self.preferences) if self.preferences else 'not specified'}",
            f"Style tags: {', '.join(self.style_tags) if self.style_tags else 'general'}",
            f"Quality focus: {', '.join(self.quality_focus) if self.quality_focus else 'schema, pacing, sources'}",
            *[f"Knowledge: {line}" for line in self.knowledge_lines],
        ]

    def to_trace_detail(self) -> str:
        return (
            f"planner_view;days={self.days};style={','.join(self.style_tags[:3]) or 'general'};"
            f"knowledge={len(self.knowledge_lines)};quality={','.join(self.quality_focus[:3]) or 'standard'}"
        )


def build_travel_planning_context(request: TripPlanRequest) -> TravelPlanningContext:
    interest_terms = _normalize_terms(_split_terms(request.interests))
    preference_terms = _normalize_terms(request.preferences)
    combined_terms = _normalize_terms((*interest_terms, *preference_terms))
    constraint_text = request.free_text_input.strip()
    style_tags = _infer_style_tags((*combined_terms, constraint_text))

    return TravelPlanningContext(
        destination=request.destination.strip(),
        days=request.days,
        budget=request.budget.strip().lower(),
        date_window=_date_window(request),
        transportation=request.transportation.strip() or "mixed transit",
        accommodation=request.accommodation.strip() or "comfortable hotel",
        interest_terms=interest_terms,
        preference_terms=preference_terms,
        style_tags=style_tags,
        constraints_present=bool(constraint_text),
    )


def build_research_context_view(context: TravelPlanningContext) -> ResearchContextView:
    return ResearchContextView(
        destination=context.destination,
        days=context.days,
        date_window=context.date_window,
        budget=context.budget,
        interests=context.interest_terms,
        preferences=context.preference_terms,
        constraints_present=context.constraints_present,
        knowledge_lines=_knowledge_prompt_lines(context),
        missing_fact_types=("attractions", "weather", "hotels", "meals"),
    )


def build_planner_context_view(
    context: TravelPlanningContext,
    quality_focus: tuple[str, ...] = (),
) -> PlannerContextView:
    return PlannerContextView(
        destination=context.destination,
        days=context.days,
        budget=context.budget,
        transportation=context.transportation,
        accommodation=context.accommodation,
        interests=context.interest_terms,
        preferences=context.preference_terms,
        style_tags=context.style_tags,
        knowledge_lines=_knowledge_prompt_lines(context),
        quality_focus=quality_focus or ("schema", "pacing", "sources", "budget"),
    )


def _knowledge_prompt_lines(context: TravelPlanningContext) -> tuple[str, ...]:
    return tuple(hit.to_prompt_line()[:500] for hit in context.retrieved_knowledge[:5])


def _split_terms(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    return tuple(item.strip() for item in TERM_SPLIT_PATTERN.split(value) if item.strip())


def _normalize_terms(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = value.strip()
        if not term:
            continue
        key = term.lower()
        if key in seen:
            continue
        normalized.append(term[:40])
        seen.add(key)
    return tuple(normalized[:12])


def _date_window(request: TripPlanRequest) -> str:
    if request.start_date and request.end_date:
        return f"{request.start_date} to {request.end_date}"
    if request.start_date:
        return f"from {request.start_date}"
    if request.end_date:
        return f"until {request.end_date}"
    return "flexible"


def _infer_style_tags(values: tuple[str, ...]) -> tuple[str, ...]:
    text = " ".join(values).lower()
    tags: list[str] = []
    if _contains_any(text, ("food", "meal", "dining", "cuisine", "\u7F8E\u98DF", "\u9910", "\u5403")):
        tags.append("food_focused")
    if _contains_any(text, ("city walk", "citywalk", "walking", "walkable", "\u8857\u533A", "\u6B65\u884C")):
        tags.append("walkable")
    if _contains_any(text, ("slow", "relaxed", "avoid packed", "\u60A0\u95F2", "\u8F7B\u677E", "\u6162")):
        tags.append("slow_paced")
    if _contains_any(text, ("nature", "lake", "mountain", "park", "\u81EA\u7136", "\u6E56", "\u5C71", "\u516C\u56ED")):
        tags.append("nature")
    if _contains_any(text, ("museum", "culture", "history", "heritage", "\u6587\u5316", "\u5386\u53F2", "\u535A\u7269\u9986")):
        tags.append("culture")
    if _contains_any(text, ("family", "kid", "children", "\u4EB2\u5B50", "\u513F\u7AE5")):
        tags.append("family_friendly")
    return tuple(tags[:6])


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
