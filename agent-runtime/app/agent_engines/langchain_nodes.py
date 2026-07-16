from __future__ import annotations

from typing import Any, Callable, TypeVar

from pydantic import TypeAdapter, ValidationError

from app.schemas import Attraction, Budget, Hotel, Meal, RouteLeg, TripPlanRequest, WeatherInfo
from app.settings import Settings
from app.travel_tools import TravelToolProvider

try:
    from langchain.agents import create_agent
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover - optional dependency.
    create_agent = None
    tool = None
    ChatOpenAI = None

T = TypeVar("T")


class LangChainTravelAgentNodeRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = self._build_model(settings)

    @property
    def enabled(self) -> bool:
        return self._model is not None and create_agent is not None and tool is not None

    def run_attraction_agent(
        self,
        request: TripPlanRequest,
        day: int,
        travel_tools: TravelToolProvider,
    ) -> list[Attraction] | None:
        return self._run_single_tool_agent(
            tool_name="search_attractions",
            tool_description="Search real attraction candidates for one itinerary day.",
            tool_call=lambda: [item.model_dump(mode="json", by_alias=True) for item in travel_tools.attractions_for_day(request, day)],
            system_prompt="You are an attraction search agent. Call the attraction search tool exactly once.",
            user_prompt=f"Find attractions for day {day} in {request.destination}. Interests: {request.interests or 'local culture'}.",
            parser=lambda value: TypeAdapter(list[Attraction]).validate_python(value),
        )

    def run_attraction_agent_for_trip(
        self,
        request: TripPlanRequest,
        travel_tools: TravelToolProvider,
    ) -> dict[int, list[Attraction]] | None:
        return self._run_single_tool_agent(
            tool_name="search_attractions_for_trip",
            tool_description="Search attraction candidates for every itinerary day.",
            tool_call=lambda: {
                day: [
                    item.model_dump(mode="json", by_alias=True)
                    for item in travel_tools.attractions_for_day(request, day)
                ]
                for day in range(1, request.days + 1)
            },
            system_prompt="You are an attraction search agent. Call the attraction search tool exactly once.",
            user_prompt=f"Find attractions for all {request.days} day(s) in {request.destination}. Interests: {request.interests or 'local culture'}.",
            parser=_parse_attractions_by_day,
        )

    def run_weather_agent(self, request: TripPlanRequest, travel_tools: TravelToolProvider) -> list[WeatherInfo] | None:
        return self._run_single_tool_agent(
            tool_name="get_weather",
            tool_description="Fetch weather forecast data for the full trip.",
            tool_call=lambda: [item.model_dump(mode="json", by_alias=True) for item in travel_tools.weather_for_trip(request)],
            system_prompt="You are a weather lookup agent. Call the weather tool exactly once.",
            user_prompt=f"Fetch weather for {request.destination} for {request.days} day(s).",
            parser=lambda value: TypeAdapter(list[WeatherInfo]).validate_python(value),
        )

    def run_hotel_agent(self, request: TripPlanRequest, day: int, travel_tools: TravelToolProvider) -> Hotel | None:
        return self._run_single_tool_agent(
            tool_name="search_hotel",
            tool_description="Search one suitable hotel candidate for one itinerary day.",
            tool_call=lambda: travel_tools.hotel_for_day(request, day).model_dump(mode="json", by_alias=True),
            system_prompt="You are a hotel recommendation agent. Call the hotel search tool exactly once.",
            user_prompt=f"Find a {request.accommodation or 'comfortable hotel'} stay for day {day} in {request.destination}.",
            parser=Hotel.model_validate,
        )

    def run_hotel_agent_for_trip(
        self,
        request: TripPlanRequest,
        travel_tools: TravelToolProvider,
    ) -> dict[int, Hotel] | None:
        return self._run_single_tool_agent(
            tool_name="search_hotels_for_trip",
            tool_description="Search one suitable hotel candidate for every itinerary day.",
            tool_call=lambda: {
                day: travel_tools.hotel_for_day(request, day).model_dump(mode="json", by_alias=True)
                for day in range(1, request.days + 1)
            },
            system_prompt="You are a hotel recommendation agent. Call the hotel search tool exactly once.",
            user_prompt=f"Find {request.accommodation or 'comfortable hotel'} stays for all {request.days} day(s) in {request.destination}.",
            parser=_parse_hotels_by_day,
        )

    def run_meal_agent(self, request: TripPlanRequest, day: int, travel_tools: TravelToolProvider) -> list[Meal] | None:
        return self._run_single_tool_agent(
            tool_name="search_meals",
            tool_description="Search breakfast, lunch, and dinner suggestions for one itinerary day.",
            tool_call=lambda: [item.model_dump(mode="json", by_alias=True) for item in travel_tools.meals_for_day(request, day)],
            system_prompt="You are a meal planning agent. Call the meal search tool exactly once.",
            user_prompt=f"Find meals for day {day} in {request.destination}. Interests: {request.interests or 'local food'}.",
            parser=lambda value: TypeAdapter(list[Meal]).validate_python(value),
        )

    def run_meal_agent_for_trip(
        self,
        request: TripPlanRequest,
        travel_tools: TravelToolProvider,
    ) -> dict[int, list[Meal]] | None:
        return self._run_single_tool_agent(
            tool_name="search_meals_for_trip",
            tool_description="Search breakfast, lunch, and dinner suggestions for every itinerary day.",
            tool_call=lambda: {
                day: [
                    item.model_dump(mode="json", by_alias=True)
                    for item in travel_tools.meals_for_day(request, day)
                ]
                for day in range(1, request.days + 1)
            },
            system_prompt="You are a meal planning agent. Call the meal search tool exactly once.",
            user_prompt=f"Find meals for all {request.days} day(s) in {request.destination}. Interests: {request.interests or 'local food'}.",
            parser=_parse_meals_by_day,
        )

    def run_route_agent(
        self,
        request: TripPlanRequest,
        day: int,
        attractions: list[Attraction],
        hotel: Hotel | None,
        travel_tools: TravelToolProvider,
    ) -> list[RouteLeg] | None:
        return self._run_single_tool_agent(
            tool_name="plan_routes",
            tool_description="Plan route legs between the hotel and attractions for one itinerary day.",
            tool_call=lambda: [
                item.model_dump(mode="json", by_alias=True)
                for item in travel_tools.routes_for_day(request, day, attractions, hotel)
            ],
            system_prompt="You are a route planning agent. Call the route planning tool exactly once.",
            user_prompt=f"Plan day {day} routes in {request.destination} using {request.transportation or 'mixed transit'}.",
            parser=lambda value: TypeAdapter(list[RouteLeg]).validate_python(value),
        )

    def run_route_agent_for_trip(
        self,
        request: TripPlanRequest,
        attractions_by_day: dict[int, list[Attraction]],
        hotels_by_day: dict[int, Hotel],
        travel_tools: TravelToolProvider,
    ) -> dict[int, list[RouteLeg]] | None:
        return self._run_single_tool_agent(
            tool_name="plan_routes_for_trip",
            tool_description="Plan route legs for every itinerary day.",
            tool_call=lambda: {
                day: [
                    item.model_dump(mode="json", by_alias=True)
                    for item in travel_tools.routes_for_day(
                        request,
                        day,
                        attractions_by_day.get(day, []),
                        hotels_by_day.get(day),
                    )
                ]
                for day in range(1, request.days + 1)
            },
            system_prompt="You are a route planning agent. Call the route planning tool exactly once.",
            user_prompt=f"Plan routes for all {request.days} day(s) in {request.destination} using {request.transportation or 'mixed transit'}.",
            parser=_parse_routes_by_day,
        )

    def run_budget_agent(self, request: TripPlanRequest, travel_tools: TravelToolProvider) -> Budget | None:
        return self._run_single_tool_agent(
            tool_name="estimate_budget",
            tool_description="Estimate the itinerary budget.",
            tool_call=lambda: travel_tools.estimate_budget(request).model_dump(mode="json", by_alias=True),
            system_prompt="You are a trip budget agent. Call the budget tool exactly once.",
            user_prompt=f"Estimate a {request.budget} budget for {request.days} day(s) in {request.destination}.",
            parser=Budget.model_validate,
        )

    def _run_single_tool_agent(
        self,
        *,
        tool_name: str,
        tool_description: str,
        tool_call: Callable[[], Any],
        system_prompt: str,
        user_prompt: str,
        parser: Callable[[Any], T],
    ) -> T | None:
        if not self.enabled or tool is None or create_agent is None:
            return None

        captured: dict[str, Any] = {}

        @tool(tool_name, description=tool_description)
        def langchain_tool() -> Any:
            """Run the wrapped travel tool and return structured JSON-compatible data."""
            captured["value"] = tool_call()
            return captured["value"]

        try:
            agent = create_agent(model=self._model, tools=[langchain_tool], system_prompt=system_prompt)
            agent.invoke({"messages": [{"role": "user", "content": user_prompt}]})
            if "value" not in captured:
                return None
            return parser(captured["value"])
        except Exception:
            return None

    @staticmethod
    def _build_model(settings: Settings) -> Any | None:
        if (
            ChatOpenAI is None
            or settings.llm_provider.lower() != "openai_compatible"
            or not settings.llm_api_key
            or not settings.llm_base_url
            or not settings.llm_model
        ):
            return None
        try:
            return ChatOpenAI(
                model=settings.llm_model,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                timeout=settings.llm_timeout_seconds,
            )
        except Exception:
            return None


def _parse_int_keyed_mapping(value: Any) -> dict[int, Any]:
    if not isinstance(value, dict):
        return {}
    parsed: dict[int, Any] = {}
    for key, item in value.items():
        try:
            day = int(key)
        except (TypeError, ValueError):
            continue
        parsed[day] = item
    return parsed


def _parse_attractions_by_day(value: Any) -> dict[int, list[Attraction]]:
    return {
        day: TypeAdapter(list[Attraction]).validate_python(items)
        for day, items in _parse_int_keyed_mapping(value).items()
    }


def _parse_hotels_by_day(value: Any) -> dict[int, Hotel]:
    return {
        day: Hotel.model_validate(item)
        for day, item in _parse_int_keyed_mapping(value).items()
    }


def _parse_meals_by_day(value: Any) -> dict[int, list[Meal]]:
    return {
        day: TypeAdapter(list[Meal]).validate_python(items)
        for day, items in _parse_int_keyed_mapping(value).items()
    }


def _parse_routes_by_day(value: Any) -> dict[int, list[RouteLeg]]:
    return {
        day: TypeAdapter(list[RouteLeg]).validate_python(items)
        for day, items in _parse_int_keyed_mapping(value).items()
    }
