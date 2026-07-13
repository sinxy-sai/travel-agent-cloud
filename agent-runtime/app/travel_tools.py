from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.schemas import Attraction, Budget, Hotel, Location, Meal, TripPlanRequest, WeatherInfo
from app.settings import Settings


class TravelToolProvider(Protocol):
    name: str

    def date_for_day(self, request: TripPlanRequest, day: int) -> str | None:
        ...

    def attractions_for_day(self, request: TripPlanRequest, day: int) -> list[Attraction]:
        ...

    def hotel_for_day(self, request: TripPlanRequest, day: int) -> Hotel:
        ...

    def meals_for_day(self, request: TripPlanRequest, day: int) -> list[Meal]:
        ...

    def weather_for_trip(self, request: TripPlanRequest) -> list[WeatherInfo]:
        ...

    def estimate_budget(self, request: TripPlanRequest) -> Budget:
        ...


@dataclass(frozen=True)
class MockTravelToolProvider:
    name: str = "mock"

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
