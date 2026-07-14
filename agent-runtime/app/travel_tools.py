from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

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


def create_travel_tool_provider(settings: Settings) -> TravelToolProvider:
    provider = settings.travel_tool_provider.strip().lower()
    if provider in {"", "mock"}:
        return MockTravelToolProvider()

    # Unknown providers intentionally degrade to mock while keeping the requested
    # name observable in logs/config for future FastMCP-backed implementations.
    return MockTravelToolProvider(name=f"mock:{provider}")


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
