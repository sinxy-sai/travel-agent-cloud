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
    days: int = Field(ge=1, le=30)
    budget: str = Field(min_length=1, max_length=40)
    interests: str = Field(default="", max_length=300)
    start_date: str | None = Field(default=None, max_length=20)
    end_date: str | None = Field(default=None, max_length=20)
    transportation: str = Field(default="", max_length=80)
    accommodation: str = Field(default="", max_length=80)
    preferences: list[str] = Field(default_factory=list, max_length=12)
    free_text_input: str = Field(default="", max_length=1000)
    conversation_id: str | None = Field(default=None, max_length=80)

    @field_validator("preferences")
    @classmethod
    def validate_preferences(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            preference = item.strip()
            if not preference or len(preference) > 40:
                continue
            key = preference.lower()
            if key not in seen:
                normalized.append(preference)
                seen.add(key)
        return normalized[:12]


class Location(APIModel):
    longitude: float
    latitude: float


class Attraction(APIModel):
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(default="", max_length=240)
    location: Location | None = None
    visit_duration: int = Field(default=120, ge=10, le=480)
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="", max_length=80)
    rating: float | None = Field(default=None, ge=0, le=5)
    image_url: str | None = Field(default=None, max_length=500)
    ticket_price: int = Field(default=0, ge=0, le=100000)


class Meal(APIModel):
    type: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(default="", max_length=240)
    location: Location | None = None
    description: str = Field(default="", max_length=1000)
    estimated_cost: int = Field(default=0, ge=0, le=100000)


class Hotel(APIModel):
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(default="", max_length=240)
    location: Location | None = None
    price_range: str = Field(default="", max_length=80)
    rating: str = Field(default="", max_length=40)
    distance: str = Field(default="", max_length=120)
    type: str = Field(default="", max_length=80)
    estimated_cost: int = Field(default=0, ge=0, le=100000)


class Budget(APIModel):
    total_attractions: int = Field(default=0, ge=0, le=10000000)
    total_hotels: int = Field(default=0, ge=0, le=10000000)
    total_meals: int = Field(default=0, ge=0, le=10000000)
    total_transportation: int = Field(default=0, ge=0, le=10000000)
    total: int = Field(default=0, ge=0, le=10000000)


class WeatherInfo(APIModel):
    date: str = Field(min_length=1, max_length=20)
    day_weather: str = Field(default="", max_length=80)
    night_weather: str = Field(default="", max_length=80)
    day_temp: int = Field(default=0, ge=-80, le=80)
    night_temp: int = Field(default=0, ge=-80, le=80)
    wind_direction: str = Field(default="", max_length=80)
    wind_power: str = Field(default="", max_length=80)


class TripDay(APIModel):
    day: int
    theme: str
    morning: str
    afternoon: str
    evening: str
    date: str | None = Field(default=None, max_length=20)
    description: str = Field(default="", max_length=1000)
    transportation: str = Field(default="", max_length=80)
    accommodation: str = Field(default="", max_length=80)
    hotel: Hotel | None = None
    attractions: list[Attraction] = Field(default_factory=list, max_length=8)
    meals: list[Meal] = Field(default_factory=list, max_length=8)


class TripPlanResponse(APIModel):
    title: str
    summary: str
    days: list[TripDay]
    tips: list[str]
    start_date: str | None = Field(default=None, max_length=20)
    end_date: str | None = Field(default=None, max_length=20)
    transportation: str = Field(default="", max_length=80)
    accommodation: str = Field(default="", max_length=80)
    preferences: list[str] = Field(default_factory=list, max_length=12)
    free_text_input: str = Field(default="", max_length=1000)
    weather_info: list[WeatherInfo] = Field(default_factory=list, max_length=30)
    overall_suggestions: str = Field(default="", max_length=4000)
    budget: Budget | None = None
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
    version: int = 1
    created_at: datetime
    updated_at: datetime | None = None


class TripPlanVersion(APIModel):
    id: str
    trip_plan_id: str
    version: int
    title: str
    plan: TripPlanResponse
    source: str
    created_at: datetime


class TripPlanVersionListResponse(APIModel):
    data: list[TripPlanVersion]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class TripPlanUpdateRequest(APIModel):
    favorite: bool | None = None
    plan: TripPlanResponse | None = None
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_update(self) -> "TripPlanUpdateRequest":
        if self.favorite is None and self.plan is None:
            raise ValueError("At least one trip plan field is required")
        if self.plan is None:
            return self
        if self.expected_version is None:
            raise ValueError("expectedVersion is required when updating plan content")
        if not self.plan.title.strip() or len(self.plan.title.strip()) > 160:
            raise ValueError("Plan title must be between 1 and 160 characters")
        if not self.plan.summary.strip() or len(self.plan.summary) > 4000:
            raise ValueError("Plan summary must be between 1 and 4000 characters")
        if not 1 <= len(self.plan.days) <= 30:
            raise ValueError("Plan must contain between 1 and 30 days")
        expected_days = list(range(1, len(self.plan.days) + 1))
        if [day.day for day in self.plan.days] != expected_days:
            raise ValueError("Plan day numbers must be sequential")
        for day in self.plan.days:
            values = [day.theme, day.morning, day.afternoon, day.evening]
            if any(not value.strip() or len(value) > 1000 for value in values):
                raise ValueError("Plan day fields must be between 1 and 1000 characters")
        if len(self.plan.tips) > 20 or any(not tip.strip() or len(tip) > 500 for tip in self.plan.tips):
            raise ValueError("Plan tips are invalid")
        return self


class TripDayRegenerateRequest(APIModel):
    instruction: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        instruction = value.strip()
        if not instruction:
            raise ValueError("Instruction is required")
        return instruction


class TripPlanReviseRequest(APIModel):
    instruction: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        instruction = value.strip()
        if not instruction:
            raise ValueError("Instruction is required")
        return instruction


class TripPlanRestoreRequest(APIModel):
    expected_version: int = Field(ge=1)


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
    password_configured: bool = True
    created_at: datetime


class AuthSession(APIModel):
    user: AuthUser


class AuthSessionInfo(APIModel):
    id: str
    user_id: str
    user_agent: str = ""
    current: bool = False
    revoked: bool = False
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


class AuthSessionListResponse(APIModel):
    data: list[AuthSessionInfo]


class AuthSessionRevokeAllResponse(APIModel):
    revoked: int


class AuthIdentity(APIModel):
    id: str
    user_id: str
    provider: str
    provider_user_id: str
    email: str = ""
    display_name: str = ""
    avatar_url: str = ""
    created_at: datetime


class AuthIdentityListResponse(APIModel):
    data: list[AuthIdentity]


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


class UserExportFile(APIModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    download_url: str


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
