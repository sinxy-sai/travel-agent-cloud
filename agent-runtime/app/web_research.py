from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Any

import httpx

from app.planning_context import TravelPlanningContext
from app.schemas import TripPlanRequest
from app.settings import Settings
from app.skills.schemas import ResearchNote


@dataclass(frozen=True)
class WebResearchResult:
    notes: tuple[ResearchNote, ...]
    source_status: str


def collect_web_research(
    request: TripPlanRequest,
    context: TravelPlanningContext | None,
    settings: Settings,
) -> WebResearchResult:
    if not settings.web_research_enabled:
        return WebResearchResult(notes=_builtin_notes(request, context), source_status="fallback")

    query = _build_query(request, context)
    searxng_notes = _search_searxng(query, settings)
    if searxng_notes:
        return WebResearchResult(notes=searxng_notes, source_status="success")
    return WebResearchResult(notes=_builtin_notes(request, context), source_status="fallback")


def _search_searxng(query: str, settings: Settings) -> tuple[ResearchNote, ...]:
    base_url = settings.searxng_base_url.strip().rstrip("/")
    if not base_url:
        return ()
    try:
        with httpx.Client(timeout=settings.web_research_timeout_seconds, follow_redirects=True) as client:
            response = client.get(
                f"{base_url}/search",
                params={"q": query, "format": "json", "language": settings.web_research_language},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return ()

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return ()

    notes: list[ResearchNote] = []
    for item in results[: settings.web_research_max_results]:
        if not isinstance(item, dict):
            continue
        title = _clean_text(str(item.get("title") or ""))[:160]
        content = _clean_text(str(item.get("content") or item.get("snippet") or ""))[:700]
        url = str(item.get("url") or "").strip()
        if not title or not content:
            continue
        notes.append(ResearchNote(title=title, summary=content, source=url or "searxng"))
    return tuple(notes)


def _builtin_notes(request: TripPlanRequest, context: TravelPlanningContext | None) -> tuple[ResearchNote, ...]:
    destination_key = request.destination.strip().lower()
    interests = (context.interest_summary if context else request.interests) or "local culture"
    generic = (
        ResearchNote(
            title=f"{request.destination} route pacing",
            summary=(
                f"For a {request.days}-day trip, group nearby stops by district and keep one flexible meal or rest block per day. "
                f"Prioritize {interests} but avoid more than three major stops in one day."
            ),
            source="builtin_research",
        ),
        ResearchNote(
            title=f"{request.destination} booking reminder",
            summary="Check opening hours, ticket rules, weather, and restaurant queues again before departure.",
            source="builtin_research",
        ),
    )
    city_notes: dict[str, tuple[ResearchNote, ...]] = {
        "chengdu": (
            ResearchNote(
                "Chengdu planning anchors",
                "Use wide-area anchors such as Kuanzhai Alley, People's Park, Wuhou Shrine/Jinli, Taikoo Li, and panda-themed stops. Food routes should leave evening flexibility.",
                "builtin_research",
            ),
        ),
        "shanghai": (
            ResearchNote(
                "Shanghai planning anchors",
                "Balance Bund/Lujiazui river views, museums, city walks in former concession areas, and family-friendly indoor backup stops.",
                "builtin_research",
            ),
        ),
        "hangzhou": (
            ResearchNote(
                "Hangzhou planning anchors",
                "Group West Lake stops by shore area and leave weather backup time for tea villages, museums, or canal-side walks.",
                "builtin_research",
            ),
        ),
        "beijing": (
            ResearchNote(
                "Beijing planning anchors",
                "Major heritage sites need security and ticket buffers. Avoid stacking more than two high-intensity historical stops in one day.",
                "builtin_research",
            ),
        ),
        "xi'an": (
            ResearchNote(
                "Xi'an planning anchors",
                "Use one strong heritage anchor per day, then pair it with a compact food or old-city walking area.",
                "builtin_research",
            ),
        ),
        "guangzhou": (
            ResearchNote(
                "Guangzhou planning anchors",
                "Food-led routes work best by district. Put dim sum, arcade streets, river views, and transit-friendly hotel areas together.",
                "builtin_research",
            ),
        ),
    }
    return (*city_notes.get(destination_key, ()), *generic)[:4]


def _build_query(request: TripPlanRequest, context: TravelPlanningContext | None) -> str:
    interest_summary = context.interest_summary if context else request.interests
    return f"{request.destination} travel guide attractions hotels food {interest_summary}".strip()


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(without_tags).split())
