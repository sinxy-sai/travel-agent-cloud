from pydantic import BaseModel, Field


class TripPlanRequest(BaseModel):
    destination: str = Field(min_length=1, max_length=80)
    days: int = Field(ge=1, le=14)
    budget: str = Field(min_length=1, max_length=40)
    interests: str = Field(default="", max_length=300)


class TripDay(BaseModel):
    day: int
    theme: str
    morning: str
    afternoon: str
    evening: str


class TripPlanResponse(BaseModel):
    title: str
    summary: str
    days: list[TripDay]
    tips: list[str]
