from __future__ import annotations

from app.plan_quality import TripPlanQualityReport, assure_trip_plan_quality
from app.planning_context import TravelPlanningContext
from app.schemas import TripPlanRequest, TripPlanResponse
from app.travel_tools import TravelToolProvider


def run_plan_quality(
    plan: TripPlanResponse,
    request: TripPlanRequest,
    travel_tools: TravelToolProvider,
    planning_context: TravelPlanningContext | None,
) -> tuple[TripPlanResponse, TripPlanQualityReport]:
    return assure_trip_plan_quality(plan, request, travel_tools, planning_context)

