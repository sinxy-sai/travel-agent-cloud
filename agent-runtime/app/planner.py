from datetime import datetime, timedelta

from app.schemas import Attraction, Budget, Hotel, Location, Meal, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse, WeatherInfo


def build_mock_trip_plan(request: TripPlanRequest) -> TripPlanResponse:
    interests = request.interests or "local culture"
    transportation = request.transportation or "mixed transit"
    accommodation = request.accommodation or "comfortable hotel"
    days = [
        TripDay(
            day=day,
            date=_date_for_day(request, day),
            theme=_theme_for_day(day, interests),
            description=f"Day {day} balances {interests} with practical transit and recovery time.",
            transportation=transportation,
            accommodation=accommodation,
            morning=f"Start with a calm neighborhood route in {request.destination} and collect local context.",
            afternoon=f"Visit a high-value attraction matched to {interests}, then leave buffer time for transit.",
            evening=f"Choose a {request.budget} dinner area and review tomorrow's route with the assistant.",
            hotel=_mock_hotel(request, day),
            attractions=_mock_attractions(request, day),
            meals=_mock_meals(request, day),
        )
        for day in range(1, request.days + 1)
    ]
    weather_info = [
        WeatherInfo(
            date=_date_for_day(request, day) or f"Day {day}",
            day_weather="Cloudy",
            night_weather="Clear",
            day_temp=24 + (day % 4),
            night_temp=16 + (day % 3),
            wind_direction="East",
            wind_power="1-3",
        )
        for day in range(1, request.days + 1)
    ]
    budget = _mock_budget(request)

    return TripPlanResponse(
        title=f"{request.days}-day {request.destination} itinerary",
        summary=(
            "This is the first mock response from the Agent Runtime. "
            "Later it will be replaced by LLM planning, tool calls, weather, maps, and RAG retrieval."
        ),
        days=days,
        start_date=request.start_date,
        end_date=request.end_date,
        transportation=transportation,
        accommodation=accommodation,
        preferences=request.preferences,
        free_text_input=request.free_text_input,
        weather_info=weather_info,
        overall_suggestions=(
            f"Use this as a structured draft for {request.destination}. "
            "Tool-backed POI, weather, route, hotel, and price enrichment will replace mock values later."
        ),
        budget=budget,
        tips=[
            "Keep the first version deterministic so frontend and deployment can be tested quickly.",
            "Add map, weather, and knowledge-base tools after the service contract is stable.",
            "Persist conversations and generated trips after authentication is introduced.",
        ],
    )


def build_mock_regenerated_trip_day(saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
    current_day = next(item for item in saved_trip_plan.plan.days if item.day == day)
    instruction_summary = instruction.strip()[:160]
    return current_day.model_copy(
        update={
            "theme": f"Adjusted: {current_day.theme}",
            "description": f"Adjusted around: {instruction_summary}",
            "morning": (
                f"Replanned around: {instruction_summary}. "
                "Start with the highest-priority stop and keep transit simple."
            ),
            "afternoon": f"Continue with a flexible activity near the morning area in {saved_trip_plan.destination}.",
            "evening": f"End with a {saved_trip_plan.budget} dinner option and leave room to adapt based on energy.",
        }
    )


def _theme_for_day(day: int, interests: str) -> str:
    themes = [
        "Arrival and orientation",
        "Culture and food",
        "Nature and slow travel",
        "Local neighborhoods",
        "Flexible discovery",
    ]
    if "food" in interests.lower():
        themes[1] = "Food-first route"
    return themes[(day - 1) % len(themes)]


def _date_for_day(request: TripPlanRequest, day: int) -> str | None:
    if not request.start_date:
        return None
    try:
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
    except ValueError:
        return None
    return (start_date + timedelta(days=day - 1)).date().isoformat()


def _mock_attractions(request: TripPlanRequest, day: int) -> list[Attraction]:
    base_lng = 104.0668
    base_lat = 30.5728
    return [
        Attraction(
            name=f"{request.destination} featured stop {day}-{index}",
            address=f"{request.destination} central area",
            location=Location(longitude=base_lng + day * 0.01 + index * 0.004, latitude=base_lat + day * 0.008 + index * 0.003),
            visit_duration=90 + index * 30,
            description=f"A mock POI matched to {request.interests or 'local culture'} for day {day}.",
            category="attraction",
            rating=4.5,
            ticket_price=40 + index * 20,
        )
        for index in range(1, 3)
    ]


def _mock_hotel(request: TripPlanRequest, day: int) -> Hotel:
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


def _mock_meals(request: TripPlanRequest, day: int) -> list[Meal]:
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


def _mock_budget(request: TripPlanRequest) -> Budget:
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
