from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class AgentMode(StrEnum):
    CHAT = "CHAT"
    TRIP_PLANNING = "TRIP_PLANNING"


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


class ConversationListResponse(APIModel):
    data: list[Conversation]
    page: int
    page_size: int
    total_items: int
    total_pages: int


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
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ConversationSummaryJob(APIModel):
    id: str
    conversation_id: str
    status: ConversationSummaryJobStatus
    event_type: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
