from app.schemas import SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse


def build_mock_trip_plan(request: TripPlanRequest) -> TripPlanResponse:
    interests = request.interests or "local culture"
    days = [
        TripDay(
            day=day,
            theme=_theme_for_day(day, interests),
            morning=f"Start with a calm neighborhood route in {request.destination} and collect local context.",
            afternoon=f"Visit a high-value attraction matched to {interests}, then leave buffer time for transit.",
            evening=f"Choose a {request.budget} dinner area and review tomorrow's route with the assistant.",
        )
        for day in range(1, request.days + 1)
    ]

    return TripPlanResponse(
        title=f"{request.days}-day {request.destination} itinerary",
        summary=(
            "This is the first mock response from the Agent Runtime. "
            "Later it will be replaced by LLM planning, tool calls, weather, maps, and RAG retrieval."
        ),
        days=days,
        tips=[
            "Keep the first version deterministic so frontend and deployment can be tested quickly.",
            "Add map, weather, and knowledge-base tools after the service contract is stable.",
            "Persist conversations and generated trips after authentication is introduced.",
        ],
    )


def build_mock_regenerated_trip_day(saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
    current_day = next(item for item in saved_trip_plan.plan.days if item.day == day)
    instruction_summary = instruction.strip()[:160]
    return TripDay(
        day=day,
        theme=f"Adjusted: {current_day.theme}",
        morning=f"Replanned around: {instruction_summary}. Start with the highest-priority stop and keep transit simple.",
        afternoon=f"Continue with a flexible activity near the morning area in {saved_trip_plan.destination}.",
        evening=f"End with a {saved_trip_plan.budget} dinner option and leave room to adapt based on energy.",
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
