from collections.abc import Callable
from typing import TypeVar

from app.agent_engines.types import TravelAgentToolCall
from app.progress import notify_trip_plan_progress
from app.schemas import Attraction, Budget, Hotel, Meal, RouteLeg, TripPlanRequest, WeatherInfo
from app.travel_tools import TravelToolDefinition, TravelToolProvider

T = TypeVar("T")


class TracingTravelToolProvider:
    def __init__(self, delegate: TravelToolProvider, tool_calls: list[TravelAgentToolCall]) -> None:
        self._delegate = delegate
        self._tool_calls = tool_calls
        self.name = delegate.name

    def list_tools(self) -> tuple[TravelToolDefinition, ...]:
        return self._delegate.list_tools()

    def date_for_day(self, request: TripPlanRequest, day: int) -> str | None:
        return self._record("date_for_day", f"day={day}", lambda: self._delegate.date_for_day(request, day))

    def attractions_for_day(self, request: TripPlanRequest, day: int) -> list[Attraction]:
        return self._record(
            "attractions_for_day",
            f"day={day}",
            lambda: self._delegate.attractions_for_day(request, day),
        )

    def hotel_for_day(self, request: TripPlanRequest, day: int) -> Hotel:
        return self._record("hotel_for_day", f"day={day}", lambda: self._delegate.hotel_for_day(request, day))

    def meals_for_day(self, request: TripPlanRequest, day: int) -> list[Meal]:
        return self._record("meals_for_day", f"day={day}", lambda: self._delegate.meals_for_day(request, day))

    def routes_for_day(
        self,
        request: TripPlanRequest,
        day: int,
        attractions: list[Attraction],
        hotel: Hotel | None = None,
    ) -> list[RouteLeg]:
        return self._record(
            "routes_for_day",
            f"day={day};stops={len(attractions)}",
            lambda: self._delegate.routes_for_day(request, day, attractions, hotel),
        )

    def weather_for_trip(self, request: TripPlanRequest) -> list[WeatherInfo]:
        return self._record("weather_for_trip", f"days={request.days}", lambda: self._delegate.weather_for_trip(request))

    def estimate_budget(self, request: TripPlanRequest) -> Budget:
        return self._record("estimate_budget", f"days={request.days}", lambda: self._delegate.estimate_budget(request))

    def _record(self, tool_name: str, detail: str, call: Callable[[], T]) -> T:
        stage_key = _stage_for_tool(tool_name)
        if stage_key:
            notify_trip_plan_progress(stage_key)
        try:
            result = call()
        except Exception:
            self._tool_calls.append(TravelAgentToolCall(tool_name=tool_name, status="FAILED", detail=detail))
            raise
        self._tool_calls.append(TravelAgentToolCall(tool_name=tool_name, status="SUCCEEDED", detail=detail))
        return result


def _stage_for_tool(tool_name: str) -> str | None:
    if tool_name == "attractions_for_day":
        return "finding_attractions"
    if tool_name == "weather_for_trip":
        return "checking_weather"
    if tool_name in {"hotel_for_day", "meals_for_day"}:
        return "selecting_stays_meals"
    if tool_name in {"routes_for_day", "estimate_budget"}:
        return "building_routes_budget"
    return None
