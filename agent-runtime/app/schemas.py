from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TripPlanRequest(APIModel):
    destination: str = Field(min_length=1, max_length=80)
    days: int = Field(ge=1, le=14)
    budget: str = Field(min_length=1, max_length=40)
    interests: str = Field(default="", max_length=300)


class TripDay(APIModel):
    day: int
    theme: str
    morning: str
    afternoon: str
    evening: str


class TripPlanResponse(APIModel):
    title: str
    summary: str
    days: list[TripDay]
    tips: list[str]


class SavedTripPlan(APIModel):
    id: str
    conversation_id: str | None = None
    title: str
    destination: str
    days: int
    budget: str
    interests: str
    plan: TripPlanResponse
    created_at: datetime


class TripPlanListResponse(APIModel):
    data: list[SavedTripPlan]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class MessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class AgentMode(StrEnum):
    CHAT = "CHAT"
    TRIP_PLANNING = "TRIP_PLANNING"


class ChatRequest(APIModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=80)
    mode: AgentMode = AgentMode.CHAT


class ChatMessage(APIModel):
    id: str
    role: MessageRole
    content: str
    created_at: datetime


class Conversation(APIModel):
    id: str
    mode: AgentMode
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessage]


class ChatResponse(APIModel):
    conversation_id: str
    message: ChatMessage
    suggestions: list[str]


class ConversationListResponse(APIModel):
    data: list[Conversation]
    page: int
    page_size: int
    total_items: int
    total_pages: int
