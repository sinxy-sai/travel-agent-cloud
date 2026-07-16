from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


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


class TripPlanListResponse(APIModel):
    data: list[SavedTripPlan]
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


class TripPlanRestoreRequest(APIModel):
    expected_version: int = Field(ge=1)
