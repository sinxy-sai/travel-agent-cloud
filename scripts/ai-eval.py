from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent-runtime"))

from app.agent_engines.langgraph import LangGraphTravelAgentEngine  # noqa: E402
from app.schemas import TripPlanRequest  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.travel_tools import MockTravelToolProvider  # noqa: E402


@dataclass(frozen=True)
class EvalCase:
    name: str
    request: TripPlanRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic AI planning eval cases.")
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    args = parser.parse_args()

    started = perf_counter()
    engine = LangGraphTravelAgentEngine(Settings(), MockTravelToolProvider())
    results = [_run_case(engine, case) for case in _cases()]
    report = {
        "status": "passed" if all(item["passed"] for item in results) else "failed",
        "caseCount": len(results),
        "passedCount": sum(1 for item in results if item["passed"]),
        "durationMs": round((perf_counter() - started) * 1000),
        "results": results,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "passed" else 1


def _run_case(engine: LangGraphTravelAgentEngine, case: EvalCase) -> dict[str, Any]:
    started = perf_counter()
    issues: list[str] = []
    plan = engine.generate_trip_plan(case.request)
    trace = engine.last_run_trace

    if len(plan.days) != case.request.days:
        issues.append("day_count_mismatch")
    if [day.day for day in plan.days] != list(range(1, case.request.days + 1)):
        issues.append("day_numbers_not_sequential")
    if not all(day.attractions for day in plan.days):
        issues.append("missing_attractions")
    if not all(day.routes for day in plan.days):
        issues.append("missing_routes")
    if not plan.weather_info:
        issues.append("missing_weather")
    if plan.budget is None or plan.budget.total <= 0:
        issues.append("missing_budget")
    if trace is None:
        issues.append("missing_trace")
    else:
        completed = set(trace.completed_nodes)
        for node in ("trip_context", "retrieve_knowledge", "research_agent", "route_budget", "planner_agent", "trip_validation"):
            if node not in completed:
                issues.append(f"missing_node:{node}")
        quality_event = next((event for event in trace.node_events if event.node_name == "trip_validation"), None)
        if quality_event is None or quality_event.score is None or not quality_event.grade:
            issues.append("missing_quality_score")

    return {
        "name": case.name,
        "passed": not issues,
        "durationMs": round((perf_counter() - started) * 1000),
        "issues": issues,
        "title": plan.title,
        "qualityScore": _latest_quality_score(trace),
        "fallbackUsed": bool(trace and trace.fallback_used),
    }


def _latest_quality_score(trace: Any) -> int | None:
    if trace is None:
        return None
    event = next((item for item in trace.node_events if item.node_name == "trip_validation"), None)
    return event.score if event else None


def _cases() -> list[EvalCase]:
    return [
        EvalCase(
            name="chengdu-culture-food",
            request=TripPlanRequest(destination="Chengdu", days=2, budget="medium", interests="culture, food"),
        ),
        EvalCase(
            name="shanghai-family",
            request=TripPlanRequest(
                destination="Shanghai",
                days=3,
                budget="high",
                interests="family, museum",
                preferences=["family friendly", "not too rushed"],
            ),
        ),
        EvalCase(
            name="hangzhou-nature",
            request=TripPlanRequest(destination="Hangzhou", days=2, budget="low", interests="nature, lake"),
        ),
        EvalCase(
            name="beijing-history",
            request=TripPlanRequest(destination="Beijing", days=4, budget="medium", interests="history, culture"),
        ),
        EvalCase(
            name="xian-short-trip",
            request=TripPlanRequest(destination="Xi'an", days=1, budget="medium", interests="heritage, food"),
        ),
        EvalCase(
            name="guangzhou-business",
            request=TripPlanRequest(
                destination="Guangzhou",
                days=2,
                budget="medium",
                interests="food, city walk",
                transportation="taxi",
                accommodation="business hotel",
            ),
        ),
    ]


if __name__ == "__main__":
    raise SystemExit(main())
