from __future__ import annotations

from app.agent_engines.langchain_nodes import LangChainTravelAgentNodeRunner
from app.schemas import Hotel, TripPlanRequest
from app.skills.schemas import ResearchBundle, SkillIssue, SkillSource, SkillTrace
from app.travel_tools import TravelToolProvider


def run_travel_research(
    request: TripPlanRequest,
    travel_tools: TravelToolProvider,
    langchain_runner: LangChainTravelAgentNodeRunner,
) -> ResearchBundle:
    """Collect the factual travel data needed before itinerary composition."""
    issues: list[SkillIssue] = []

    attractions_by_day = langchain_runner.run_attraction_agent_for_trip(request, travel_tools)
    attraction_source = _source("attractions", attractions_by_day is not None, langchain_runner.enabled)
    if attractions_by_day is None:
        attractions_by_day = {
            day: travel_tools.attractions_for_day(request, day)
            for day in range(1, request.days + 1)
        }

    weather_info = langchain_runner.run_weather_agent(request, travel_tools)
    weather_source = _source("weather", weather_info is not None, langchain_runner.enabled)
    if weather_info is None:
        weather_info = travel_tools.weather_for_trip(request)

    hotels_by_day = langchain_runner.run_hotel_agent_for_trip(request, travel_tools)
    hotel_source = _source("hotels", hotels_by_day is not None, langchain_runner.enabled)
    if hotels_by_day is None:
        hotels_by_day = {
            day: travel_tools.hotel_for_day(request, day)
            for day in range(1, request.days + 1)
        }

    meals_by_day = langchain_runner.run_meal_agent_for_trip(request, travel_tools)
    meal_source = _source("meals", meals_by_day is not None, langchain_runner.enabled)
    if meals_by_day is None:
        meals_by_day = {
            day: travel_tools.meals_for_day(request, day)
            for day in range(1, request.days + 1)
        }

    _add_missing_day_issues("attractions", request.days, attractions_by_day, issues)
    _add_missing_day_issues("hotels", request.days, hotels_by_day, issues)
    _add_missing_day_issues("meals", request.days, meals_by_day, issues)
    if not weather_info:
        issues.append(SkillIssue(code="weather_missing", message="Weather data was not returned."))

    status = "success" if not issues else "partial"
    return ResearchBundle(
        attractions_by_day=attractions_by_day,
        weather_info=weather_info,
        hotels_by_day=hotels_by_day,
        meals_by_day=meals_by_day,
        trace=SkillTrace(
            name="travel_research",
            status=status,
            sources=(attraction_source, weather_source, hotel_source, meal_source),
            issues=tuple(issues),
        ),
    )


def _source(name: str, used_langchain_agent: bool, langchain_enabled: bool) -> SkillSource:
    if used_langchain_agent:
        return SkillSource(provider=f"langchain:{name}", status="success", detail="tool_calling_agent")
    if langchain_enabled:
        return SkillSource(provider=f"travel_tools:{name}", status="fallback", detail="agent_call_failed")
    return SkillSource(provider=f"travel_tools:{name}", status="success", detail="direct_tool_call")


def _add_missing_day_issues(
    name: str,
    days: int,
    values: dict[int, object] | dict[int, list[object]] | dict[int, Hotel],
    issues: list[SkillIssue],
) -> None:
    missing_days = [str(day) for day in range(1, days + 1) if not values.get(day)]
    if missing_days:
        issues.append(
            SkillIssue(
                code=f"{name}_missing_days",
                message=f"{name} missing for day(s): {', '.join(missing_days)}.",
            )
        )

