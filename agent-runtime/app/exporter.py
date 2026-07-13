from app.schemas import SavedTripPlan, TripPlanResponse


def trip_plan_to_markdown(plan: TripPlanResponse, title: str | None = None) -> str:
    lines: list[str] = [
        f"# {title or plan.title}",
        "",
        plan.summary,
        "",
    ]

    overview: list[str] = []
    if plan.start_date:
        overview.append(f"- Start date: {plan.start_date}")
    if plan.end_date:
        overview.append(f"- End date: {plan.end_date}")
    if plan.transportation:
        overview.append(f"- Transportation: {plan.transportation}")
    if plan.accommodation:
        overview.append(f"- Accommodation: {plan.accommodation}")
    if plan.preferences:
        overview.append(f"- Preferences: {', '.join(plan.preferences)}")
    if plan.free_text_input:
        overview.append(f"- Constraints: {plan.free_text_input}")

    if overview:
        lines.extend(["## Overview", "", *overview, ""])

    if plan.budget:
        lines.extend(
            [
                "## Budget",
                "",
                f"- Attractions: {plan.budget.total_attractions}",
                f"- Hotels: {plan.budget.total_hotels}",
                f"- Meals: {plan.budget.total_meals}",
                f"- Transportation: {plan.budget.total_transportation}",
                f"- Total: {plan.budget.total}",
                "",
            ]
        )

    if plan.weather_info:
        lines.extend(["## Weather", ""])
        for weather in plan.weather_info:
            lines.append(
                f"- {weather.date}: {weather.day_weather} / {weather.night_weather}, "
                f"{weather.day_temp}C / {weather.night_temp}C, "
                f"{weather.wind_direction} wind {weather.wind_power}"
            )
        lines.append("")

    if plan.overall_suggestions:
        lines.extend(["## Overall suggestions", "", plan.overall_suggestions, ""])

    lines.extend(["## Itinerary", ""])

    for day in plan.days:
        heading = f"### Day {day.day}: {day.theme}"
        if day.date:
            heading += f" ({day.date})"
        lines.extend(
            [
                heading,
                "",
            ]
        )
        if day.description:
            lines.extend([day.description, ""])
        if day.transportation:
            lines.append(f"- Transportation: {day.transportation}")
        if day.accommodation:
            lines.append(f"- Accommodation: {day.accommodation}")
        if day.hotel:
            hotel_parts = [day.hotel.name]
            if day.hotel.address:
                hotel_parts.append(day.hotel.address)
            if day.hotel.price_range:
                hotel_parts.append(f"price {day.hotel.price_range}")
            if day.hotel.estimated_cost:
                hotel_parts.append(f"estimated {day.hotel.estimated_cost}")
            lines.append(f"- Hotel: {'; '.join(hotel_parts)}")
        if day.transportation or day.accommodation or day.hotel:
            lines.append("")

        if day.attractions:
            lines.extend(["#### Attractions", ""])
            for attraction in day.attractions:
                lines.append(f"- {attraction.name}")
                if attraction.address:
                    lines.append(f"  - Address: {attraction.address}")
                if attraction.category:
                    lines.append(f"  - Category: {attraction.category}")
                if attraction.visit_duration:
                    lines.append(f"  - Visit duration: {attraction.visit_duration} minutes")
                if attraction.rating is not None:
                    lines.append(f"  - Rating: {attraction.rating}")
                if attraction.ticket_price:
                    lines.append(f"  - Ticket price: {attraction.ticket_price}")
                if attraction.description:
                    lines.append(f"  - Notes: {attraction.description}")
            lines.append("")

        if day.meals:
            lines.extend(["#### Meals", ""])
            for meal in day.meals:
                meal_line = f"- {meal.type}: {meal.name}"
                if meal.estimated_cost:
                    meal_line += f" ({meal.estimated_cost})"
                lines.append(meal_line)
                if meal.address:
                    lines.append(f"  - Address: {meal.address}")
                if meal.description:
                    lines.append(f"  - Notes: {meal.description}")
            lines.append("")

        lines.extend(
            [
                "#### Daily rhythm",
                "",
                f"- Morning: {day.morning}",
                f"- Afternoon: {day.afternoon}",
                f"- Evening: {day.evening}",
                "",
            ]
        )

    if plan.tips:
        lines.extend(["## Travel notes", ""])
        lines.extend([f"- {tip}" for tip in plan.tips])
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def saved_trip_plan_to_markdown(saved_trip_plan: SavedTripPlan) -> str:
    header = [
        f"# {saved_trip_plan.title}",
        "",
        f"- Destination: {saved_trip_plan.destination}",
        f"- Days: {saved_trip_plan.days}",
        f"- Budget: {saved_trip_plan.budget}",
    ]

    if saved_trip_plan.interests:
        header.append(f"- Interests: {saved_trip_plan.interests}")

    header.extend(["", "---", ""])
    return "\n".join(header) + trip_plan_to_markdown(saved_trip_plan.plan, title=saved_trip_plan.plan.title)
