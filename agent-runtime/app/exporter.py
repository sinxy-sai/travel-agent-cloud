from app.schemas import SavedTripPlan, TripPlanResponse


def trip_plan_to_markdown(plan: TripPlanResponse, title: str | None = None) -> str:
    lines: list[str] = [
        f"# {title or plan.title}",
        "",
        plan.summary,
        "",
        "## Itinerary",
        "",
    ]

    for day in plan.days:
        lines.extend(
            [
                f"### Day {day.day}: {day.theme}",
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
