from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class AuthRegisterRequest(APIModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=80)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("Valid email is required")
        return email

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        return value.strip()


class AuthLoginRequest(APIModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthPasswordChangeRequest(APIModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Password cannot start or end with whitespace")
        return value


class AuthEmailRequest(APIModel):
    email: str = Field(min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthTokenConfirmRequest(APIModel):
    token: str = Field(min_length=20, max_length=300)


class AuthPasswordResetConfirmRequest(APIModel):
    token: str = Field(min_length=20, max_length=300)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Password cannot start or end with whitespace")
        return value


class AuthEmailActionResponse(APIModel):
    sent: bool
    delivery: str
    expires_at: datetime | None = None
    dev_token: str | None = None
    action_url: str | None = None


class AuthAccountDeleteRequest(APIModel):
    current_password: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=6, max_length=32)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        confirmation = value.strip().upper()
        if confirmation != "DELETE":
            raise ValueError("Confirmation must be DELETE")
        return confirmation


class AuthUserUpdateRequest(APIModel):
    display_name: str = Field(default="", max_length=80)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        return value.strip()


class AuthUser(APIModel):
    id: str
    email: str
    display_name: str = ""
    email_verified: bool = False
    created_at: datetime


class AuthSession(APIModel):
    user: AuthUser


class UserSecurityEvent(APIModel):
    id: str
    event_type: str
    details: dict = Field(default_factory=dict)
    created_at: datetime


class UserSecurityEventListResponse(APIModel):
    data: list[UserSecurityEvent]
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


class UserDataExport(APIModel):
    exported_at: datetime
    user: AuthUser
    profile: UserProfile
    conversations: list[Conversation]
    conversation_summaries: list[ConversationSummary]
    trip_plans: list[SavedTripPlan]


class UserDataImportRequest(UserDataExport):
    @model_validator(mode="after")
    def validate_import_size(self) -> "UserDataImportRequest":
        message_count = sum(len(conversation.messages) for conversation in self.conversations)
        if len(self.conversations) > 200:
            raise ValueError("Cannot import more than 200 conversations at once")
        if message_count > 5000:
            raise ValueError("Cannot import more than 5000 messages at once")
        if len(self.conversation_summaries) > 200:
            raise ValueError("Cannot import more than 200 conversation summaries at once")
        if len(self.trip_plans) > 500:
            raise ValueError("Cannot import more than 500 trip plans at once")
        return self


class UserDataImportResponse(APIModel):
    imported_at: datetime
    profile_imported: bool
    conversations_imported: int
    conversation_summaries_imported: int
    trip_plans_imported: int
    skipped_items: int


class AnonymousDataSummary(APIModel):
    has_data: bool
    conversations: int
    conversation_summaries: int
    trip_plans: int


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
