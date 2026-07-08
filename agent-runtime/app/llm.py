import json
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.schemas import AgentMode, ChatMessage, MessageRole, TripPlanRequest, TripPlanResponse
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

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse | None:
        if not self.enabled:
            return None

        schema_hint = {
            "title": "3-day Chengdu itinerary",
            "summary": "Short overview",
            "days": [
                {
                    "day": 1,
                    "theme": "Arrival and food walk",
                    "morning": "Plan text",
                    "afternoon": "Plan text",
                    "evening": "Plan text",
                }
            ],
            "tips": ["Practical tip"],
        }
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
                    f"Create a {request.days}-day itinerary for {request.destination}. "
                    f"Budget: {request.budget}. Interests: {request.interests or 'local culture'}. "
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
