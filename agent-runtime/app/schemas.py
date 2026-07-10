from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    conversation_id: str | None = Field(default=None, max_length=80)


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
    saved_trip_plan_id: str | None = None
    conversation_id: str | None = None


class SavedTripPlan(APIModel):
    id: str
    conversation_id: str | None = None
    title: str
    destination: str
    days: int
    budget: str
    interests: str
    plan: TripPlanResponse
    favorite: bool = False
    created_at: datetime


class TripPlanUpdateRequest(APIModel):
    favorite: bool


class TripPlanListResponse(APIModel):
    data: list[SavedTripPlan]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class UserProfile(APIModel):
    user_id: str
    display_name: str = ""
    home_city: str = ""
    preferred_budget: str = ""
    travel_style: str = ""
    interests: list[str] = Field(default_factory=list)
    updated_at: datetime


class UserProfileUpdateRequest(APIModel):
    display_name: str | None = Field(default=None, max_length=80)
    home_city: str | None = Field(default=None, max_length=80)
    preferred_budget: str | None = Field(default=None, max_length=40)
    travel_style: str | None = Field(default=None, max_length=80)
    interests: list[str] | None = Field(default=None, max_length=12)

    @field_validator("display_name", "home_city", "preferred_budget", "travel_style")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None

        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            interest = item.strip()
            if not interest or len(interest) > 40:
                continue
            key = interest.lower()
            if key not in seen:
                normalized.append(interest)
                seen.add(key)
        return normalized[:12]


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


class ConversationUpdateRequest(APIModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title is required")
        return title


class ConversationSummary(APIModel):
    id: str
    conversation_id: str
    summary: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationSummaryJobStatus(StrEnum):
    QUEUED = "QUEUED"


class ConversationSummaryJob(APIModel):
    conversation_id: str
    status: ConversationSummaryJobStatus
    event_type: str


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
