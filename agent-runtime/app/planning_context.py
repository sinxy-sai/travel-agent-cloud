import re
from dataclasses import dataclass

from app.schemas import TripPlanRequest


TERM_SPLIT_PATTERN = re.compile("[,\uFF0C;\uFF1B\u3001|/]+")


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
        ]

    def to_trace_detail(self) -> str:
        tags = ",".join(self.style_tags[:3]) if self.style_tags else "general"
        return (
            f"days={self.days}; interests={len(self.interest_terms)}; "
            f"preferences={len(self.preference_terms)}; constraints={'yes' if self.constraints_present else 'no'}; "
            f"tags={tags}"
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
