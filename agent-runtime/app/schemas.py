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


class RouteLeg(APIModel):
    from_name: str = Field(min_length=1, max_length=160)
    to_name: str = Field(min_length=1, max_length=160)
    mode: str = Field(default="", max_length=80)
    distance_meters: int = Field(default=0, ge=0, le=1000000)
    duration_minutes: int = Field(default=0, ge=0, le=10000)
    estimated_cost: int = Field(default=0, ge=0, le=100000)
    instruction: str = Field(default="", max_length=500)


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
    routes: list[RouteLeg] = Field(default_factory=list, max_length=16)


class TripPlanDataSourceStatus(StrEnum):
    LIVE = "LIVE"
    FALLBACK = "FALLBACK"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class TripPlanDataSource(APIModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    status: TripPlanDataSourceStatus
    detail: str = Field(default="", max_length=500)
    tool_names: list[str] = Field(default_factory=list, max_length=12)


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
    data_sources: list[TripPlanDataSource] = Field(default_factory=list, max_length=12)
    saved_trip_plan_id: str | None = None
    conversation_id: str | None = None


class TripPlanJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class TripPlanJobStageStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class TripPlanJobStage(APIModel):
    key: str
    label: str
    detail: str
    status: TripPlanJobStageStatus


class TripPlanJob(APIModel):
    id: str
    status: TripPlanJobStatus
    current_stage_key: str
    stages: list[TripPlanJobStage]
    plan: TripPlanResponse | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


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


class RuntimeTripPlanReviseRequest(TripPlanReviseRequest):
    saved_trip_plan: SavedTripPlan


class RuntimeTripDayRegenerateRequest(TripDayRegenerateRequest):
    saved_trip_plan: SavedTripPlan


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
