from app.agent_engines.types import TravelAgentRunTrace
from app.schemas import TripPlanDataSource, TripPlanDataSourceStatus


DATA_SOURCE_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("attractions", "Attractions", ("attractions_for_day",)),
    ("weather", "Weather", ("weather_for_trip",)),
    ("lodging_meals", "Hotels and meals", ("hotel_for_day", "meals_for_day")),
    ("routes", "Routes", ("routes_for_day",)),
    ("budget", "Budget", ("estimate_budget",)),
)


def summarize_trip_plan_data_sources(trace: TravelAgentRunTrace | None) -> list[TripPlanDataSource]:
    if trace is None:
        return [
            TripPlanDataSource(
                key=key,
                label=label,
                status=TripPlanDataSourceStatus.UNKNOWN,
                detail="No agent trace was available for this section.",
                tool_names=list(tool_names),
            )
            for key, label, tool_names in DATA_SOURCE_GROUPS
        ]

    sources: list[TripPlanDataSource] = []
    for key, label, tool_names in DATA_SOURCE_GROUPS:
        calls = [call for call in trace.tool_calls if call.tool_name in tool_names]
        succeeded = [call for call in calls if call.status == "SUCCEEDED"]
        failed = [call for call in calls if call.status == "FAILED"]
        if succeeded:
            status = TripPlanDataSourceStatus.LIVE
            detail = f"{len(succeeded)} live tool call(s) succeeded."
        elif failed:
            status = TripPlanDataSourceStatus.FAILED
            detail = f"{len(failed)} tool call(s) failed; fallback data may be shown."
        elif trace.fallback_used:
            status = TripPlanDataSourceStatus.FALLBACK
            detail = "Generated from deterministic fallback data for this run."
        else:
            status = TripPlanDataSourceStatus.UNKNOWN
            detail = "No matching tool call was recorded for this section."
        sources.append(
            TripPlanDataSource(
                key=key,
                label=label,
                status=status,
                detail=detail,
                tool_names=list(tool_names),
            )
        )
    return sources
