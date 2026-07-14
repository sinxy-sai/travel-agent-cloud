import json
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.planning_context import TravelPlanningContext, build_travel_planning_context
from app.schemas import AgentMode, ChatMessage, MessageRole, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse
from app.settings import Settings


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return (
            self.settings.llm_provider.lower() == "openai_compatible"
            and bool(self.settings.llm_api_key)
            and bool(self.settings.llm_base_url)
            and bool(self.settings.llm_model)
        )

    def generate_chat_reply(self, messages: list[ChatMessage], mode: AgentMode) -> str | None:
        if not self.enabled:
            return None

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You are Travel Agent Cloud, a practical AI travel assistant. "
                    "Reply in the user's language. Help users plan realistic trips with routes, timing, budget awareness, "
                    "local food, transit, and constraints. Do not claim to book tickets or hotels. "
                    "Ask concise follow-up questions when key constraints are missing."
                ),
            }
        ]

        for message in messages[-10:]:
            prompt_messages.append(
                {
                    "role": _message_role(message.role),
                    "content": message.content,
                }
            )

        if mode == AgentMode.TRIP_PLANNING:
            prompt_messages.append(
                {
                    "role": "system",
                    "content": "For trip planning requests, prefer a clear day-by-day structure and practical next steps.",
                }
            )

        content = self._chat_completion(prompt_messages, response_format=None)
        return _trim_text(content) if content else None

    def generate_trip_plan(
        self,
        request: TripPlanRequest,
        planning_context: TravelPlanningContext | None = None,
    ) -> TripPlanResponse | None:
        if not self.enabled:
            return None
        planning_context = planning_context or build_travel_planning_context(request)

        schema_hint = {
            "title": "3-day Chengdu itinerary",
            "summary": "Short overview",
            "startDate": "2026-08-01",
            "endDate": "2026-08-03",
            "transportation": "mixed transit",
            "accommodation": "comfortable hotel",
            "preferences": ["local food", "city walk"],
            "days": [
                {
                    "day": 1,
                    "date": "2026-08-01",
                    "theme": "Arrival and food walk",
                    "description": "Day overview",
                    "transportation": "mixed transit",
                    "accommodation": "comfortable hotel",
                    "morning": "Plan text",
                    "afternoon": "Plan text",
                    "evening": "Plan text",
                    "hotel": {
                        "name": "Hotel name",
                        "address": "Hotel address",
                        "location": {"longitude": 104.0668, "latitude": 30.5728},
                        "priceRange": "400-700",
                        "rating": "4.5",
                        "distance": "Near the route",
                        "type": "comfortable hotel",
                        "estimatedCost": 520,
                    },
                    "attractions": [
                        {
                            "name": "Attraction name",
                            "address": "Attraction address",
                            "location": {"longitude": 104.0668, "latitude": 30.5728},
                            "visitDuration": 120,
                            "description": "Why to visit",
                            "category": "attraction",
                            "rating": 4.5,
                            "ticketPrice": 60,
                        }
                    ],
                    "meals": [
                        {"type": "breakfast", "name": "Breakfast option", "description": "Local breakfast", "estimatedCost": 25},
                        {"type": "lunch", "name": "Lunch option", "description": "Local lunch", "estimatedCost": 55},
                        {"type": "dinner", "name": "Dinner option", "description": "Local dinner", "estimatedCost": 90},
                    ],
                }
            ],
            "weatherInfo": [
                {
                    "date": "2026-08-01",
                    "dayWeather": "Cloudy",
                    "nightWeather": "Clear",
                    "dayTemp": 26,
                    "nightTemp": 18,
                    "windDirection": "East",
                    "windPower": "1-3",
                }
            ],
            "overallSuggestions": "Practical route notes",
            "budget": {
                "totalAttractions": 180,
                "totalHotels": 1200,
                "totalMeals": 480,
                "totalTransportation": 200,
                "total": 2060,
            },
            "tips": ["Practical tip"],
        }
        planning_context_prompt = "\n".join(planning_context.to_prompt_lines())
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a travel itinerary planner. Return only valid JSON matching the requested schema. "
                    "No markdown fences, no commentary outside JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create an itinerary from this normalized planning context:\n"
                    f"{planning_context_prompt}\n"
                    f"Additional constraints: {request.free_text_input or 'none'}. "
                    "Include hotel, attractions, meals, weatherInfo, overallSuggestions, and budget when possible. "
                    f"JSON schema example: {json.dumps(schema_hint, ensure_ascii=False)}"
                ),
            },
        ]

        content = self._chat_completion(messages, response_format={"type": "json_object"}) or self._chat_completion(
            messages,
            response_format=None,
        )
        if not content:
            return None

        try:
            payload = json.loads(_extract_json(content))
            return TripPlanResponse.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError):
            return None

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay | None:
        if not self.enabled:
            return None

        current_day = next((item for item in saved_trip_plan.plan.days if item.day == day), None)
        if current_day is None:
            return None

        schema_hint = {
            "day": day,
            "date": "2026-08-01",
            "theme": "Updated day theme",
            "description": "Updated day overview",
            "transportation": "mixed transit",
            "accommodation": "comfortable hotel",
            "morning": "Updated morning plan",
            "afternoon": "Updated afternoon plan",
            "evening": "Updated evening plan",
            "hotel": current_day.hotel.model_dump(mode="json", by_alias=True) if current_day.hotel else None,
            "attractions": [item.model_dump(mode="json", by_alias=True) for item in current_day.attractions],
            "meals": [item.model_dump(mode="json", by_alias=True) for item in current_day.meals],
        }
        itinerary = saved_trip_plan.plan.model_dump(mode="json", by_alias=True)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a travel itinerary replanning agent. Return only valid JSON for one itinerary day. "
                    "Preserve the requested day number. Do not include markdown fences or commentary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Update only day {day} of this itinerary. "
                    f"Destination: {saved_trip_plan.destination}. Budget: {saved_trip_plan.budget}. "
                    f"Interests: {saved_trip_plan.interests or 'local culture'}. "
                    f"User instruction: {instruction}. "
                    f"Current day: {current_day.model_dump(mode='json', by_alias=True)}. "
                    f"Full itinerary context: {json.dumps(itinerary, ensure_ascii=False)}. "
                    f"JSON schema example: {json.dumps(schema_hint, ensure_ascii=False)}"
                ),
            },
        ]

        content = self._chat_completion(messages, response_format={"type": "json_object"}) or self._chat_completion(
            messages,
            response_format=None,
        )
        if not content:
            return None

        try:
            payload = json.loads(_extract_json(content))
            payload["day"] = day
            return TripDay.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError):
            return None

    def revise_trip_plan(self, saved_trip_plan: SavedTripPlan, instruction: str) -> TripPlanResponse | None:
        if not self.enabled:
            return None

        current_plan = saved_trip_plan.plan
        schema_hint = current_plan.model_dump(mode="json", by_alias=True)
        schema_hint["title"] = "Revised itinerary title"
        schema_hint["summary"] = "Revised itinerary overview"
        itinerary = current_plan.model_dump(mode="json", by_alias=True)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a travel itinerary revision agent. Return only valid JSON for the full itinerary. "
                    "Preserve the same response schema, keep day numbers sequential, and do not include markdown fences."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Revise this itinerary according to the user instruction. "
                    f"Destination: {saved_trip_plan.destination}. Budget: {saved_trip_plan.budget}. "
                    f"Interests: {saved_trip_plan.interests or 'local culture'}. "
                    f"User instruction: {instruction}. "
                    f"Current itinerary: {json.dumps(itinerary, ensure_ascii=False)}. "
                    f"JSON schema example: {json.dumps(schema_hint, ensure_ascii=False)}"
                ),
            },
        ]

        content = self._chat_completion(messages, response_format={"type": "json_object"}) or self._chat_completion(
            messages,
            response_format=None,
        )
        if not content:
            return None

        try:
            payload = json.loads(_extract_json(content))
            payload["savedTripPlanId"] = saved_trip_plan.id
            payload["conversationId"] = saved_trip_plan.conversation_id
            return TripPlanResponse.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError):
            return None

    def _chat_completion(self, messages: list[dict[str, Any]], response_format: dict[str, str] | None) -> str | None:
        endpoint = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        try:
            with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
                response = client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self.settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return None

        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        return content if isinstance(content, str) else None


def _message_role(role: MessageRole) -> str:
    if role == MessageRole.ASSISTANT:
        return "assistant"
    if role == MessageRole.SYSTEM:
        return "system"
    return "user"


def _extract_json(content: str) -> str:
    normalized = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", normalized, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return normalized


def _trim_text(content: str) -> str:
    normalized = content.strip()
    return normalized[:4000] if len(normalized) > 4000 else normalized
