from __future__ import annotations

from app.agent_engines.langchain_nodes import LangChainTravelAgentNodeRunner
from app.planning_context import TravelPlanningContext
from app.schemas import Attraction, Hotel, TripPlanRequest
from app.skills.schemas import RouteBudgetBundle, SkillIssue, SkillSource, SkillTrace
from app.travel_tools import TravelToolProvider


def run_route_budget(
    request: TripPlanRequest,
    attractions_by_day: dict[int, list[Attraction]],
    hotels_by_day: dict[int, Hotel],
    travel_tools: TravelToolProvider,
    langchain_runner: LangChainTravelAgentNodeRunner,
    planning_context: TravelPlanningContext | None = None,
) -> RouteBudgetBundle:
    """Plan route legs and estimate budget from researched candidates."""
    issues: list[SkillIssue] = []

    routes_by_day = langchain_runner.run_route_agent_for_trip(
        request,
        attractions_by_day,
        hotels_by_day,
        travel_tools,
    )
    route_source = _source("routes", routes_by_day is not None, langchain_runner.enabled)
    if routes_by_day is None:
        routes_by_day = {}
        for day in range(1, request.days + 1):
            routes_by_day[day] = travel_tools.routes_for_day(
                request,
                day,
                attractions_by_day.get(day, []),
                hotels_by_day.get(day),
            )

    budget = langchain_runner.run_budget_agent(request, travel_tools)
    budget_source = _source("budget", budget is not None, langchain_runner.enabled)
    if budget is None:
        budget = travel_tools.estimate_budget(request)

    missing_route_days = [str(day) for day in range(1, request.days + 1) if not routes_by_day.get(day)]
    if missing_route_days:
        issues.append(
            SkillIssue(
                code="routes_missing_days",
                message=f"Routes missing for day(s): {', '.join(missing_route_days)}.",
            )
        )
    if budget is None:
        issues.append(SkillIssue(code="budget_missing", message="Budget estimate was not returned."))

    if budget and budget.total <= 0:
        issues.append(SkillIssue(code="budget_total_invalid", message="Budget total must be greater than zero.", severity="error"))

    status = "success" if not issues else "partial"
    return RouteBudgetBundle(
        routes_by_day=routes_by_day,
        budget=budget,
        trace=SkillTrace(
            name="route_budget",
            status=status,
            sources=(route_source, budget_source),
            issues=tuple(issues),
        ),
    )


def _source(name: str, used_langchain_agent: bool, langchain_enabled: bool) -> SkillSource:
    if used_langchain_agent:
        return SkillSource(provider=f"langchain:{name}", status="success", detail="tool_calling_agent")
    if langchain_enabled:
        return SkillSource(provider=f"travel_tools:{name}", status="fallback", detail="agent_call_failed")
    return SkillSource(provider=f"travel_tools:{name}", status="success", detail="direct_tool_call")
