from dataclasses import dataclass

from app.planning_context import TravelPlanningContext, build_travel_planning_context
from app.planner import build_mock_trip_plan
from app.schemas import TripDay, TripPlanRequest, TripPlanResponse
from app.travel_tools import MockTravelToolProvider, TravelToolProvider


ISSUE_WEIGHTS = {
    "days_count_mismatch": 30,
    "day_numbers_not_sequential": 20,
    "missing_start_date": 8,
    "missing_end_date": 8,
    "missing_transportation": 5,
    "missing_accommodation": 5,
    "missing_preferences": 5,
    "missing_weather": 8,
    "missing_budget": 10,
    "missing_routes": 4,
    "missing_attractions": 12,
    "missing_meals": 8,
    "missing_hotel": 6,
    "day_overloaded": 6,
    "internal_placeholder_text": 20,
    "missing_overall_suggestions": 4,
    "missing_tips": 3,
}

INTERNAL_PLACEHOLDER_TERMS = (
    "Amap POI",
    "Stub",
    "Replace with Amap",
    "scenic district",
    "featured stop",
    "mock POI",
    "Mock ",
    "MCP stay",
    "MCP option",
)


@dataclass(frozen=True)
class TripPlanQualityReport:
    issues: tuple[str, ...]
    repaired_fields: tuple[str, ...]

    @property
    def repaired(self) -> bool:
        return bool(self.repaired_fields)

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def score(self) -> int:
        penalty = sum(ISSUE_WEIGHTS.get(issue, 5) for issue in self.issues)
        return max(0, 100 - penalty)

    @property
    def grade(self) -> str:
        if self.score >= 90:
            return "ready"
        if self.score >= 70:
            return "review"
        return "needs_work"

    def to_trace_detail(self) -> str:
        issue_summary = ",".join(self.issues[:4]) if self.issues else "none"
        repair_summary = ",".join(self.repaired_fields[:4]) if self.repaired_fields else "none"
        return (
            f"issues={len(self.issues)}:{issue_summary}; "
            f"repaired={len(self.repaired_fields)}:{repair_summary}; "
            f"score={self.score}; grade={self.grade}"
        )


def assure_trip_plan_quality(
    plan: TripPlanResponse,
    request: TripPlanRequest,
    travel_tools: TravelToolProvider | None = None,
    planning_context: TravelPlanningContext | None = None,
) -> tuple[TripPlanResponse, TripPlanQualityReport]:
    travel_tools = travel_tools or MockTravelToolProvider()
    planning_context = planning_context or build_travel_planning_context(request)
    issues = _quality_issues(plan, request, planning_context)
    repaired_fields: list[str] = []
    repaired_plan = plan

    if "days_count_mismatch" in issues or "day_numbers_not_sequential" in issues:
        fallback_plan = build_mock_trip_plan(request, travel_tools, planning_context)
        repaired_plan = repaired_plan.model_copy(update={"days": fallback_plan.days})
        repaired_fields.append("days")

    update: dict[str, object] = {}
    if "missing_start_date" in issues and request.start_date:
        update["start_date"] = request.start_date
        repaired_fields.append("start_date")
    if "missing_end_date" in issues and request.end_date:
        update["end_date"] = request.end_date
        repaired_fields.append("end_date")
    if "missing_transportation" in issues:
        update["transportation"] = planning_context.transportation
        repaired_fields.append("transportation")
    if "missing_accommodation" in issues:
        update["accommodation"] = planning_context.accommodation
        repaired_fields.append("accommodation")
    if "missing_preferences" in issues and planning_context.preference_terms:
        update["preferences"] = list(planning_context.preference_terms)
        repaired_fields.append("preferences")
    if "missing_weather" in issues:
        update["weather_info"] = travel_tools.weather_for_trip(request)
        repaired_fields.append("weather_info")
    if "missing_budget" in issues:
        update["budget"] = travel_tools.estimate_budget(request)
        repaired_fields.append("budget")
    if "missing_routes" in issues:
        update["days"] = _repair_day_routes(repaired_plan, request, travel_tools)
        repaired_fields.append("routes")
    if "missing_attractions" in issues or "missing_meals" in issues or "missing_hotel" in issues:
        update["days"] = _repair_day_content(
            update.get("days") if isinstance(update.get("days"), list) else repaired_plan.days,
            request,
            travel_tools,
        )
        repaired_fields.append("day_content")
    if "missing_overall_suggestions" in issues:
        update["overall_suggestions"] = "Review weather, transit buffers, and reservation windows before departure."
        repaired_fields.append("overall_suggestions")
    if "missing_tips" in issues:
        update["tips"] = ["Review the itinerary before departure and keep buffer time for transit."]
        repaired_fields.append("tips")

    if update:
        repaired_plan = repaired_plan.model_copy(update=update)

    return repaired_plan, TripPlanQualityReport(
        issues=tuple(issues),
        repaired_fields=tuple(repaired_fields),
    )


def _quality_issues(
    plan: TripPlanResponse,
    request: TripPlanRequest,
    planning_context: TravelPlanningContext,
) -> list[str]:
    issues: list[str] = []

    if len(plan.days) != request.days:
        issues.append("days_count_mismatch")
    if [day.day for day in plan.days] != list(range(1, len(plan.days) + 1)):
        issues.append("day_numbers_not_sequential")
    if request.start_date and not plan.start_date:
        issues.append("missing_start_date")
    if request.end_date and not plan.end_date:
        issues.append("missing_end_date")
    if not plan.transportation:
        issues.append("missing_transportation")
    if not plan.accommodation:
        issues.append("missing_accommodation")
    if planning_context.preference_terms and not plan.preferences:
        issues.append("missing_preferences")
    if not plan.weather_info:
        issues.append("missing_weather")
    if plan.budget is None:
        issues.append("missing_budget")
    if any(not day.routes for day in plan.days):
        issues.append("missing_routes")
    if any(not day.attractions for day in plan.days):
        issues.append("missing_attractions")
    if any(not day.meals for day in plan.days):
        issues.append("missing_meals")
    if any(day.hotel is None for day in plan.days):
        issues.append("missing_hotel")
    if any(len(day.attractions or []) > 5 for day in plan.days):
        issues.append("day_overloaded")
    if _contains_internal_placeholder_text(plan):
        issues.append("internal_placeholder_text")
    if not plan.overall_suggestions.strip():
        issues.append("missing_overall_suggestions")
    if not plan.tips:
        issues.append("missing_tips")

    return issues


def _contains_internal_placeholder_text(plan: TripPlanResponse) -> bool:
    text_parts = [
        plan.title,
        plan.summary,
        plan.overall_suggestions,
        *plan.tips,
    ]
    for day in plan.days:
        text_parts.extend((day.theme, day.morning, day.afternoon, day.evening, day.description))
        if day.hotel:
            text_parts.extend((day.hotel.name, day.hotel.address, day.hotel.type))
        for attraction in day.attractions or []:
            text_parts.extend((attraction.name, attraction.address, attraction.description, attraction.category))
        for meal in day.meals or []:
            text_parts.extend((meal.type, meal.name, meal.address, meal.description))
        for route in day.routes or []:
            text_parts.extend((route.from_name, route.to_name, route.mode, route.instruction))
    serialized = "\n".join(part for part in text_parts if part)
    return any(term in serialized for term in INTERNAL_PLACEHOLDER_TERMS)


def _repair_day_routes(
    plan: TripPlanResponse,
    request: TripPlanRequest,
    travel_tools: TravelToolProvider,
) -> list[TripDay]:
    repaired_days: list[TripDay] = []
    for day in plan.days:
        if day.routes:
            repaired_days.append(day)
            continue
        hotel = day.hotel or travel_tools.hotel_for_day(request, day.day)
        attractions = day.attractions or travel_tools.attractions_for_day(request, day.day)
        repaired_days.append(
            day.model_copy(
                update={
                    "hotel": hotel,
                    "attractions": attractions,
                    "routes": travel_tools.routes_for_day(request, day.day, attractions, hotel),
                }
            )
        )
    return repaired_days


def _repair_day_content(
    days: list[TripDay],
    request: TripPlanRequest,
    travel_tools: TravelToolProvider,
) -> list[TripDay]:
    repaired_days: list[TripDay] = []
    for day in days:
        hotel = day.hotel or travel_tools.hotel_for_day(request, day.day)
        attractions = day.attractions or travel_tools.attractions_for_day(request, day.day)
        meals = day.meals or travel_tools.meals_for_day(request, day.day)
        repaired_days.append(
            day.model_copy(
                update={
                    "hotel": hotel,
                    "attractions": attractions,
                    "meals": meals,
                }
            )
        )
    return repaired_days
