from __future__ import annotations

from datetime import datetime, timedelta

from app.planning_context import TravelPlanningContext, build_planner_context_view, build_travel_planning_context
from app.schemas import Attraction, Budget, Hotel, Meal, RouteLeg, TripDay, TripPlanRequest, TripPlanResponse, WeatherInfo
from app.skills.schemas import ResearchNote


def compose_trip_plan(
    *,
    request: TripPlanRequest,
    planning_context: TravelPlanningContext | None,
    draft_plan: TripPlanResponse | None,
    attractions_by_day: dict[int, list[Attraction]],
    weather_info: list[WeatherInfo],
    hotels_by_day: dict[int, Hotel],
    meals_by_day: dict[int, list[Meal]],
    research_notes: tuple[ResearchNote, ...],
    routes_by_day: dict[int, list[RouteLeg]],
    budget: Budget | None,
) -> TripPlanResponse:
    context = planning_context or build_travel_planning_context(request)
    planner_view = build_planner_context_view(context)
    draft_days = {day.day: day for day in draft_plan.days} if draft_plan else {}
    days: list[TripDay] = []

    for day_number in range(1, request.days + 1):
        draft_day = draft_days.get(day_number)
        hotel = hotels_by_day.get(day_number) or (draft_day.hotel if draft_day else None)
        attractions = attractions_by_day.get(day_number) or (draft_day.attractions if draft_day else [])
        meals = meals_by_day.get(day_number) or (draft_day.meals if draft_day else [])
        routes = routes_by_day.get(day_number) or (draft_day.routes if draft_day else [])
        days.append(
            TripDay(
                day=day_number,
                date=(draft_day.date if draft_day else None) or _date_for_day(request, day_number),
                theme=(draft_day.theme if draft_day else "") or _theme_for_day(day_number, context),
                description=(
                    (draft_day.description if draft_day else "")
                    or _day_description(day_number, context, research_notes)
                ),
                transportation=(draft_day.transportation if draft_day else "") or context.transportation,
                accommodation=(draft_day.accommodation if draft_day else "") or context.accommodation,
                morning=(draft_day.morning if draft_day else "") or _default_day_part("Morning", request, context),
                afternoon=(draft_day.afternoon if draft_day else "") or _default_day_part("Afternoon", request, context),
                evening=(draft_day.evening if draft_day else "") or _default_day_part("Evening", request, context),
                hotel=hotel,
                attractions=attractions,
                meals=meals,
                routes=routes,
            )
        )

    return TripPlanResponse(
        title=(draft_plan.title if draft_plan else "") or f"{request.days}-day {request.destination} itinerary",
        summary=(
            (draft_plan.summary if draft_plan else "")
            or f"A {context.date_window} itinerary for {context.destination}, planned from agent-collected travel data."
        ),
        days=days,
        tips=(draft_plan.tips if draft_plan and draft_plan.tips else [
            "Confirm attraction opening hours before departure.",
            "Keep transit buffer time between high-priority stops.",
            "Review weather and reservation needs before each travel day.",
        ]),
        start_date=(draft_plan.start_date if draft_plan else None) or request.start_date,
        end_date=(draft_plan.end_date if draft_plan else None) or request.end_date,
        transportation=(draft_plan.transportation if draft_plan else "") or context.transportation,
        accommodation=(draft_plan.accommodation if draft_plan else "") or context.accommodation,
        preferences=(draft_plan.preferences if draft_plan else []) or list(context.preference_terms),
        free_text_input=(draft_plan.free_text_input if draft_plan else "") or request.free_text_input,
        weather_info=weather_info or (draft_plan.weather_info if draft_plan else []),
        overall_suggestions=_overall_suggestions(draft_plan, planner_view, research_notes),
        budget=budget or (draft_plan.budget if draft_plan else None),
    )


def _date_for_day(request: TripPlanRequest, day: int) -> str | None:
    if not request.start_date:
        return None
    try:
        start_date = datetime.fromisoformat(request.start_date)
    except ValueError:
        return None
    return (start_date + timedelta(days=day - 1)).replace(hour=0, minute=0, second=0, microsecond=0).date().isoformat()


def _theme_for_day(day: int, planning_context: TravelPlanningContext) -> str:
    themes = [
        "Arrival and orientation",
        "Food-first route",
        "Culture and local neighborhoods",
        "Nature and slow travel",
        "Flexible discovery",
    ]
    if "culture" in planning_context.style_tags:
        themes[1] = "Culture and heritage"
    if "nature" in planning_context.style_tags:
        themes[2] = "Parks and outdoor time"
    return themes[(day - 1) % len(themes)]


def _default_day_part(part: str, request: TripPlanRequest, planning_context: TravelPlanningContext) -> str:
    if part == "Morning":
        return f"Start with a focused route in {request.destination} around {planning_context.interest_summary}."
    if part == "Afternoon":
        return "Continue with nearby stops and keep enough buffer for transit."
    return "Use the evening for a moderate dinner area and a review of the next day's route."


def _day_description(day: int, planning_context: TravelPlanningContext, research_notes: tuple[ResearchNote, ...]) -> str:
    note = research_notes[(day - 1) % len(research_notes)] if research_notes else None
    if note:
        return f"Day {day} balances {planning_context.interest_summary} with practical pacing. Research note: {note.summary[:220]}"
    return f"Day {day} balances {planning_context.interest_summary} with practical pacing."


def _overall_suggestions(
    draft_plan: TripPlanResponse | None,
    planner_view,
    research_notes: tuple[ResearchNote, ...],
) -> str:
    if draft_plan and draft_plan.overall_suggestions:
        return draft_plan.overall_suggestions
    knowledge_note = (
        f" Applied {len(planner_view.knowledge_lines)} retrieved planning note(s)."
        if planner_view.knowledge_lines
        else ""
    )
    research_note = (
        " Research highlights: "
        + " ".join(f"{note.title}: {note.summary[:140]}" for note in research_notes[:2])
        if research_notes
        else ""
    )
    quality_note = ", ".join(planner_view.quality_focus[:3])
    return (
        "This itinerary was assembled from research, route-budget, and planner skill outputs. "
        f"Quality focus: {quality_note}.{knowledge_note}{research_note}"
    )
