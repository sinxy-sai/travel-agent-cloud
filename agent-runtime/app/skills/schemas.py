from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import Attraction, Budget, Hotel, Meal, RouteLeg, WeatherInfo


SkillStatus = str


@dataclass(frozen=True)
class SkillIssue:
    code: str
    message: str
    severity: str = "warning"


@dataclass(frozen=True)
class SkillSource:
    provider: str
    status: SkillStatus
    detail: str = ""


@dataclass(frozen=True)
class SkillTrace:
    name: str
    status: SkillStatus
    sources: tuple[SkillSource, ...] = ()
    issues: tuple[SkillIssue, ...] = ()

    def to_detail(self) -> str:
        source_summary = ",".join(f"{source.provider}:{source.status}" for source in self.sources) or "none"
        issue_summary = f";issues={len(self.issues)}" if self.issues else ""
        return f"skill={self.name};status={self.status};sources={source_summary}{issue_summary}"


@dataclass(frozen=True)
class ResearchBundle:
    attractions_by_day: dict[int, list[Attraction]] = field(default_factory=dict)
    weather_info: list[WeatherInfo] = field(default_factory=list)
    hotels_by_day: dict[int, Hotel] = field(default_factory=dict)
    meals_by_day: dict[int, list[Meal]] = field(default_factory=dict)
    trace: SkillTrace = field(
        default_factory=lambda: SkillTrace(name="travel_research", status="failed"),
    )


@dataclass(frozen=True)
class RouteBudgetBundle:
    routes_by_day: dict[int, list[RouteLeg]] = field(default_factory=dict)
    budget: Budget | None = None
    trace: SkillTrace = field(
        default_factory=lambda: SkillTrace(name="route_budget", status="failed"),
    )

