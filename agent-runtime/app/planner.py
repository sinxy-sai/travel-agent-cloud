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
    days: list[TripDay] = []
    for day in range(1, request.days + 1):
        hotel = travel_tools.hotel_for_day(request, day)
        attractions = travel_tools.attractions_for_day(request, day)
        days.append(
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
                hotel=hotel,
                attractions=attractions,
                meals=travel_tools.meals_for_day(request, day),
                routes=travel_tools.routes_for_day(request, day, attractions, hotel),
            )
        )
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
    days = []
    for day in plan.days:
        hotel = day.hotel or travel_tools.hotel_for_day(request, day.day)
        attractions = day.attractions or travel_tools.attractions_for_day(request, day.day)
        days.append(
            day.model_copy(
                update={
                    "date": day.date or travel_tools.date_for_day(request, day.day),
                    "description": day.description
                    or f"Day {day.day} balances {planning_context.interest_summary} with practical pacing.",
                    "transportation": day.transportation or transportation,
                    "accommodation": day.accommodation or accommodation,
                    "hotel": hotel,
                    "attractions": attractions,
                    "meals": day.meals or travel_tools.meals_for_day(request, day.day),
                    "routes": day.routes or travel_tools.routes_for_day(request, day.day, attractions, hotel),
                }
            )
        )

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


def build_mock_revised_trip_plan(saved_trip_plan: SavedTripPlan, instruction: str) -> TripPlanResponse:
    instruction_summary = instruction.strip()[:220]
    current_plan = saved_trip_plan.plan
    revised_days = [
        day.model_copy(
            update={
                "theme": _revised_theme(day.theme),
                "description": _append_revision_note(day.description, instruction_summary),
                "morning": _append_revision_note(day.morning, instruction_summary),
                "afternoon": _append_revision_note(day.afternoon, instruction_summary),
                "evening": _append_revision_note(day.evening, instruction_summary),
            }
        )
        for day in current_plan.days
    ]
    tips = [
        *[tip for tip in current_plan.tips if tip.strip()],
        f"Revision applied: {instruction_summary}",
    ][:20]

    return current_plan.model_copy(
        update={
            "title": _revised_title(current_plan.title),
            "summary": _append_revision_note(current_plan.summary, instruction_summary),
            "days": revised_days,
            "overall_suggestions": _append_revision_note(current_plan.overall_suggestions, instruction_summary),
            "tips": tips,
            "saved_trip_plan_id": saved_trip_plan.id,
            "conversation_id": saved_trip_plan.conversation_id,
        }
    )


def trip_plan_request_from_saved(saved_trip_plan: SavedTripPlan, instruction: str = "") -> TripPlanRequest:
    plan = saved_trip_plan.plan
    free_text_input = plan.free_text_input or ""
    if instruction.strip():
        free_text_input = f"{free_text_input[:700]}\nRevision instruction: {instruction.strip()[:260]}".strip()
    free_text_input = free_text_input[:1000]
    return TripPlanRequest(
        destination=saved_trip_plan.destination,
        days=max(1, len(plan.days) or saved_trip_plan.days),
        budget=saved_trip_plan.budget,
        interests=saved_trip_plan.interests,
        start_date=plan.start_date,
        end_date=plan.end_date,
        transportation=plan.transportation,
        accommodation=plan.accommodation,
        preferences=plan.preferences,
        free_text_input=free_text_input,
        conversation_id=saved_trip_plan.conversation_id,
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


def _revised_title(title: str) -> str:
    normalized = title.strip() or "Trip itinerary"
    if normalized.lower().startswith("revised "):
        return normalized[:160]
    return f"Revised {normalized}"[:160]


def _revised_theme(theme: str) -> str:
    normalized = theme.strip() or "Updated day"
    if normalized.lower().startswith("revised "):
        return normalized[:160]
    return f"Revised {normalized}"[:160]


def _append_revision_note(value: str, instruction_summary: str) -> str:
    normalized = value.strip()
    note = f"Adjusted for: {instruction_summary}"
    if not normalized:
        return note[:1000]
    if note in normalized:
        return normalized[:1000]
    return f"{normalized} {note}"[:1000]
