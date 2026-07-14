from app.planning_context import TravelPlanningContext, build_travel_planning_context
from app.schemas import SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse
from app.travel_tools import MockTravelToolProvider, TravelToolProvider


def build_mock_trip_plan(
    request: TripPlanRequest,
    travel_tools: TravelToolProvider | None = None,
    planning_context: TravelPlanningContext | None = None,
) -> TripPlanResponse:
    travel_tools = travel_tools or MockTravelToolProvider()
    planning_context = planning_context or build_travel_planning_context(request)
    interests = planning_context.interest_summary
    transportation = planning_context.transportation
    accommodation = planning_context.accommodation
    days = [
        TripDay(
            day=day,
            date=travel_tools.date_for_day(request, day),
            theme=_theme_for_day(day, interests),
            description=f"Day {day} balances {interests} with practical transit and recovery time.",
            transportation=transportation,
            accommodation=accommodation,
            morning=f"Start with a calm neighborhood route in {request.destination} and collect local context.",
            afternoon=f"Visit a high-value attraction matched to {interests}, then leave buffer time for transit.",
            evening=f"Choose a {request.budget} dinner area and review tomorrow's route with the assistant.",
            hotel=travel_tools.hotel_for_day(request, day),
            attractions=travel_tools.attractions_for_day(request, day),
            meals=travel_tools.meals_for_day(request, day),
        )
        for day in range(1, request.days + 1)
    ]
    weather_info = travel_tools.weather_for_trip(request)
    budget = travel_tools.estimate_budget(request)

    return TripPlanResponse(
        title=f"{request.days}-day {request.destination} itinerary",
        summary=(
            f"A structured {planning_context.date_window} draft for {planning_context.destination}, "
            f"optimized for {interests}."
        ),
        days=days,
        start_date=request.start_date,
        end_date=request.end_date,
        transportation=transportation,
        accommodation=accommodation,
        preferences=list(planning_context.preference_terms),
        free_text_input=request.free_text_input,
        weather_info=weather_info,
        overall_suggestions=(
            f"Use this as a structured draft for {planning_context.destination}. "
            f"Planning style: {', '.join(planning_context.style_tags) if planning_context.style_tags else 'general'}. "
            "Tool-backed POI, weather, route, hotel, and price enrichment will replace mock values later."
        ),
        budget=budget,
        tips=[
            "Keep the first version deterministic so frontend and deployment can be tested quickly.",
            "Add map, weather, and knowledge-base tools after the service contract is stable.",
            "Persist conversations and generated trips after authentication is introduced.",
        ],
    )


def enrich_trip_plan_response(
    plan: TripPlanResponse,
    request: TripPlanRequest,
    travel_tools: TravelToolProvider | None = None,
    planning_context: TravelPlanningContext | None = None,
) -> TripPlanResponse:
    travel_tools = travel_tools or MockTravelToolProvider()
    planning_context = planning_context or build_travel_planning_context(request)
    transportation = plan.transportation or planning_context.transportation
    accommodation = plan.accommodation or planning_context.accommodation
    days = [
        day.model_copy(
            update={
                "date": day.date or travel_tools.date_for_day(request, day.day),
                "description": day.description
                or f"Day {day.day} balances {planning_context.interest_summary} with practical pacing.",
                "transportation": day.transportation or transportation,
                "accommodation": day.accommodation or accommodation,
                "hotel": day.hotel or travel_tools.hotel_for_day(request, day.day),
                "attractions": day.attractions or travel_tools.attractions_for_day(request, day.day),
                "meals": day.meals or travel_tools.meals_for_day(request, day.day),
            }
        )
        for day in plan.days
    ]

    return plan.model_copy(
        update={
            "start_date": plan.start_date or request.start_date,
            "end_date": plan.end_date or request.end_date,
            "transportation": transportation,
            "accommodation": accommodation,
            "preferences": plan.preferences or list(planning_context.preference_terms),
            "free_text_input": plan.free_text_input or request.free_text_input,
            "weather_info": plan.weather_info or travel_tools.weather_for_trip(request),
            "overall_suggestions": plan.overall_suggestions
            or "Review weather, transit buffers, and reservation windows before departure.",
            "budget": plan.budget or travel_tools.estimate_budget(request),
            "days": days,
        }
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
