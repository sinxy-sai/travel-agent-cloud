from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from typing import Any, Protocol

import httpx
from pydantic import TypeAdapter, ValidationError

from app.schemas import Attraction, Budget, Hotel, Location, Meal, RouteLeg, TripPlanRequest, WeatherInfo
from app.settings import Settings


@dataclass(frozen=True)
class TravelToolDefinition:
    name: str
    category: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
        }


class TravelToolProvider(Protocol):
    name: str

    def list_tools(self) -> tuple[TravelToolDefinition, ...]:
        ...

    def date_for_day(self, request: TripPlanRequest, day: int) -> str | None:
        ...

    def attractions_for_day(self, request: TripPlanRequest, day: int) -> list[Attraction]:
        ...

    def hotel_for_day(self, request: TripPlanRequest, day: int) -> Hotel:
        ...

    def meals_for_day(self, request: TripPlanRequest, day: int) -> list[Meal]:
        ...

    def routes_for_day(
        self,
        request: TripPlanRequest,
        day: int,
        attractions: list[Attraction],
        hotel: Hotel | None = None,
    ) -> list[RouteLeg]:
        ...

    def weather_for_trip(self, request: TripPlanRequest) -> list[WeatherInfo]:
        ...

    def estimate_budget(self, request: TripPlanRequest) -> Budget:
        ...


@dataclass(frozen=True)
class MockTravelToolProvider:
    name: str = "mock"

    def list_tools(self) -> tuple[TravelToolDefinition, ...]:
        return (
            TravelToolDefinition(
                name="date_for_day",
                category="calendar",
                description="Derives the itinerary date for a day when a trip start date is available.",
            ),
            TravelToolDefinition(
                name="attractions_for_day",
                category="poi",
                description="Returns deterministic mock attractions for an itinerary day.",
            ),
            TravelToolDefinition(
                name="hotel_for_day",
                category="lodging",
                description="Returns a deterministic mock hotel matched to destination and budget.",
            ),
            TravelToolDefinition(
                name="meals_for_day",
                category="food",
                description="Returns deterministic mock meal suggestions for breakfast, lunch, and dinner.",
            ),
            TravelToolDefinition(
                name="routes_for_day",
                category="route",
                description="Returns deterministic mock route legs between the hotel and daily attractions.",
            ),
            TravelToolDefinition(
                name="weather_for_trip",
                category="weather",
                description="Returns deterministic mock weather for the trip duration.",
            ),
            TravelToolDefinition(
                name="estimate_budget",
                category="budget",
                description="Estimates itinerary costs from mock attractions, hotel, meals, and transit.",
            ),
        )

    def date_for_day(self, request: TripPlanRequest, day: int) -> str | None:
        if not request.start_date:
            return None
        try:
            start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        except ValueError:
            return None
        return (start_date + timedelta(days=day - 1)).date().isoformat()

    def attractions_for_day(self, request: TripPlanRequest, day: int) -> list[Attraction]:
        base_lng = 104.0668
        base_lat = 30.5728
        return [
            Attraction(
                name=f"{request.destination} featured stop {day}-{index}",
                address=f"{request.destination} central area",
                location=Location(
                    longitude=base_lng + day * 0.01 + index * 0.004,
                    latitude=base_lat + day * 0.008 + index * 0.003,
                ),
                visit_duration=90 + index * 30,
                description=f"A mock POI matched to {request.interests or 'local culture'} for day {day}.",
                category="attraction",
                rating=4.5,
                ticket_price=40 + index * 20,
            )
            for index in range(1, 3)
        ]

    def hotel_for_day(self, request: TripPlanRequest, day: int) -> Hotel:
        return Hotel(
            name=f"{request.destination} {request.accommodation or 'comfort'} stay {day}",
            address=f"{request.destination} transit-friendly district",
            location=Location(longitude=104.0668 + day * 0.006, latitude=30.5728 + day * 0.006),
            price_range=_hotel_price_range(request.budget),
            rating="4.5",
            distance="Within 20 minutes of the main route",
            type=request.accommodation or "comfortable hotel",
            estimated_cost=_hotel_cost(request.budget),
        )

    def meals_for_day(self, request: TripPlanRequest, day: int) -> list[Meal]:
        costs = {"breakfast": 25, "lunch": 55, "dinner": 90}
        return [
            Meal(
                type=meal_type,
                name=f"{request.destination} {meal_type} option {day}",
                description=f"Local {meal_type} matched to {request.interests or 'general travel'}.",
                estimated_cost=cost,
            )
            for meal_type, cost in costs.items()
        ]

    def routes_for_day(
        self,
        request: TripPlanRequest,
        day: int,
        attractions: list[Attraction],
        hotel: Hotel | None = None,
    ) -> list[RouteLeg]:
        if not attractions:
            return []

        mode = request.transportation or "mixed transit"
        start_name = hotel.name if hotel is not None else f"{request.destination} hotel area"
        stops = [start_name, *[attraction.name for attraction in attractions], start_name]
        return [
            RouteLeg(
                from_name=stops[index],
                to_name=stops[index + 1],
                mode=mode,
                distance_meters=1800 + day * 250 + index * 650,
                duration_minutes=18 + day * 2 + index * 8,
                estimated_cost=_route_leg_cost(mode, index),
                instruction=f"Mock {mode} route from {stops[index]} to {stops[index + 1]}.",
            )
            for index in range(len(stops) - 1)
        ]

    def weather_for_trip(self, request: TripPlanRequest) -> list[WeatherInfo]:
        return [
            WeatherInfo(
                date=self.date_for_day(request, day) or f"Day {day}",
                day_weather="Cloudy",
                night_weather="Clear",
                day_temp=24 + (day % 4),
                night_temp=16 + (day % 3),
                wind_direction="East",
                wind_power="1-3",
            )
            for day in range(1, request.days + 1)
        ]

    def estimate_budget(self, request: TripPlanRequest) -> Budget:
        attraction_total = request.days * 100
        hotel_total = request.days * _hotel_cost(request.budget)
        meal_total = request.days * 170
        transportation_total = request.days * 60
        return Budget(
            total_attractions=attraction_total,
            total_hotels=hotel_total,
            total_meals=meal_total,
            total_transportation=transportation_total,
            total=attraction_total + hotel_total + meal_total + transportation_total,
        )


class FastMCPTravelToolProvider:
    name = "fastmcp"

    def __init__(self, settings: Settings, fallback: TravelToolProvider | None = None) -> None:
        self._settings = settings
        self._fallback = fallback or MockTravelToolProvider(name="mock:fastmcp_fallback")
        self._client = _FastMCPToolClient(settings)

    def list_tools(self) -> tuple[TravelToolDefinition, ...]:
        return (
            TravelToolDefinition(
                name="date_for_day",
                category="calendar",
                description="Derives the itinerary date locally before FastMCP travel tool enrichment.",
            ),
            TravelToolDefinition(
                name="attractions_for_day",
                category="poi",
                description=f"Calls FastMCP tool {self._settings.fastmcp_attractions_tool}; falls back to mock POI data.",
            ),
            TravelToolDefinition(
                name="hotel_for_day",
                category="lodging",
                description=f"Calls FastMCP tool {self._settings.fastmcp_hotel_tool}; falls back to mock hotel data.",
            ),
            TravelToolDefinition(
                name="meals_for_day",
                category="food",
                description=f"Calls FastMCP tool {self._settings.fastmcp_meals_tool}; falls back to mock meal data.",
            ),
            TravelToolDefinition(
                name="routes_for_day",
                category="route",
                description=f"Calls FastMCP tool {self._settings.fastmcp_routes_tool}; falls back to mock route data.",
            ),
            TravelToolDefinition(
                name="weather_for_trip",
                category="weather",
                description=f"Calls FastMCP tool {self._settings.fastmcp_weather_tool}; falls back to mock weather data.",
            ),
            TravelToolDefinition(
                name="estimate_budget",
                category="budget",
                description=f"Calls FastMCP tool {self._settings.fastmcp_budget_tool}; falls back to mock budget data.",
            ),
        )

    def date_for_day(self, request: TripPlanRequest, day: int) -> str | None:
        return self._fallback.date_for_day(request, day)

    def attractions_for_day(self, request: TripPlanRequest, day: int) -> list[Attraction]:
        arguments = {
            "destination": request.destination,
            "day": day,
            "days": request.days,
            "interests": request.interests,
            "preferences": request.preferences,
            "budget": request.budget,
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_attractions_tool, arguments)
            return _validate_list(payload, Attraction)
        except FastMCPToolError:
            return self._fallback.attractions_for_day(request, day)

    def hotel_for_day(self, request: TripPlanRequest, day: int) -> Hotel:
        arguments = {
            "destination": request.destination,
            "day": day,
            "budget": request.budget,
            "accommodation": request.accommodation,
            "transportation": request.transportation,
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_hotel_tool, arguments)
            return Hotel.model_validate(payload)
        except (FastMCPToolError, ValidationError, TypeError):
            return self._fallback.hotel_for_day(request, day)

    def meals_for_day(self, request: TripPlanRequest, day: int) -> list[Meal]:
        arguments = {
            "destination": request.destination,
            "day": day,
            "interests": request.interests,
            "budget": request.budget,
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_meals_tool, arguments)
            return _validate_list(payload, Meal)
        except FastMCPToolError:
            return self._fallback.meals_for_day(request, day)

    def routes_for_day(
        self,
        request: TripPlanRequest,
        day: int,
        attractions: list[Attraction],
        hotel: Hotel | None = None,
    ) -> list[RouteLeg]:
        arguments = {
            "destination": request.destination,
            "day": day,
            "transportation": request.transportation,
            "hotel": hotel.model_dump(mode="json", by_alias=True) if hotel else None,
            "attractions": [item.model_dump(mode="json", by_alias=True) for item in attractions],
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_routes_tool, arguments)
            return _validate_list(payload, RouteLeg)
        except FastMCPToolError:
            return self._fallback.routes_for_day(request, day, attractions, hotel)

    def weather_for_trip(self, request: TripPlanRequest) -> list[WeatherInfo]:
        arguments = {
            "destination": request.destination,
            "startDate": request.start_date,
            "endDate": request.end_date,
            "days": request.days,
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_weather_tool, arguments)
            return _validate_list(payload, WeatherInfo)
        except FastMCPToolError:
            return self._fallback.weather_for_trip(request)

    def estimate_budget(self, request: TripPlanRequest) -> Budget:
        arguments = {
            "destination": request.destination,
            "days": request.days,
            "budget": request.budget,
            "transportation": request.transportation,
            "accommodation": request.accommodation,
        }
        try:
            payload = self._client.call_tool(self._settings.fastmcp_budget_tool, arguments)
            return Budget.model_validate(payload)
        except (FastMCPToolError, ValidationError, TypeError):
            return self._fallback.estimate_budget(request)


class FastMCPToolError(RuntimeError):
    pass


class _FastMCPToolClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.fastmcp_base_url.strip().rstrip("/")
        self._auth_token = settings.fastmcp_auth_token
        self._timeout_seconds = settings.fastmcp_timeout_seconds

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self._base_url:
            raise FastMCPToolError("FastMCP base URL is not configured")

        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        payload = {
            "jsonrpc": "2.0",
            "id": f"travel-agent-cloud:{tool_name}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(self._base_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FastMCPToolError("FastMCP tool call failed") from exc

        if isinstance(data, dict) and data.get("error"):
            raise FastMCPToolError("FastMCP tool returned an error")
        return _extract_tool_result(data)


def create_travel_tool_provider(settings: Settings) -> TravelToolProvider:
    provider = settings.travel_tool_provider.strip().lower()
    if provider in {"", "mock"}:
        return MockTravelToolProvider()
    if provider in {"fastmcp", "mcp"}:
        if settings.fastmcp_base_url.strip():
            return FastMCPTravelToolProvider(settings)
        return MockTravelToolProvider(name="mock:fastmcp_unconfigured")

    # Unknown providers intentionally degrade to mock while keeping the requested
    # name observable in logs/config for future FastMCP-backed implementations.
    return MockTravelToolProvider(name=f"mock:{provider}")


def _extract_tool_result(data: Any) -> Any:
    result = data.get("result") if isinstance(data, dict) else data
    if isinstance(result, dict):
        if "structuredContent" in result:
            return result["structuredContent"]
        if "data" in result:
            return result["data"]
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                text = first.get("text")
                if isinstance(text, str):
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
        return result
    return result


def _validate_list(value: Any, item_type: type) -> list:
    payload = value.get("items") if isinstance(value, dict) and "items" in value else value
    try:
        return TypeAdapter(list[item_type]).validate_python(payload)
    except (ValidationError, TypeError) as exc:
        raise FastMCPToolError("FastMCP tool returned invalid list payload") from exc


def _hotel_price_range(budget: str) -> str:
    normalized = budget.lower()
    if normalized in {"premium", "luxury", "high"}:
        return "800-1200"
    if normalized in {"low", "economy", "budget"}:
        return "200-350"
    return "400-700"


def _hotel_cost(budget: str) -> int:
    normalized = budget.lower()
    if normalized in {"premium", "luxury", "high"}:
        return 950
    if normalized in {"low", "economy", "budget"}:
        return 280
    return 520


def _route_leg_cost(mode: str, index: int) -> int:
    normalized = mode.lower()
    if normalized in {"walk", "walking", "bike", "bicycle", "cycling", "on foot"}:
        return 0
    if any(keyword in normalized for keyword in ("taxi", "ride", "car")):
        return 25 + index * 10
    return 3 + index * 2
