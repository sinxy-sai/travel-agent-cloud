from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent-runtime"))

from dotenv import load_dotenv  # noqa: E402


def _disable_compose_database_url_for_local_windows() -> None:
    database_url = os.getenv("DATABASE_URL", "")
    if platform.system().lower() == "windows" and "@postgres:" in database_url:
        os.environ["DATABASE_URL"] = ""


load_dotenv(ROOT / "agent-runtime" / ".env")
_disable_compose_database_url_for_local_windows()
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_API_KEY"] = ""

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
    parser.add_argument("--database-url", help="Optional runtime RAG database URL override.")
    parser.add_argument("--require-rag-backend", choices=("static", "postgres"), help="Fail unless every case uses this RAG backend.")
    parser.add_argument("--base-url", help="Optional running gateway/runtime URL for HTTP eval mode.")
    parser.add_argument("--user-id", default=f"ai-eval-{uuid4().hex}", help="User id header used in HTTP eval mode.")
    parser.add_argument("--case", action="append", dest="case_names", help="Run only the named eval case. Can be repeated.")
    parser.add_argument("--case-limit", type=int, default=0, help="Run only the first N eval cases after filtering.")
    args = parser.parse_args()
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    started = perf_counter()
    cases = _selected_cases(args.case_names, args.case_limit)
    if args.base_url:
        results = [_run_http_case(args.base_url.rstrip("/"), args.user_id, case) for case in cases]
    else:
        engine = LangGraphTravelAgentEngine(Settings(), MockTravelToolProvider())
        results = [_run_case(engine, case) for case in cases]
    if args.require_rag_backend:
        for result in results:
            if result["ragBackend"] != args.require_rag_backend:
                result["passed"] = False
                result["issues"].append(f"rag_backend_not_{args.require_rag_backend}")
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
    if "Research" not in (plan.overall_suggestions or ""):
        issues.append("missing_research_notes_in_plan")
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
        if _rag_backend(trace) in {"missing", "unknown"}:
            issues.append("missing_rag_backend")

    return {
        "name": case.name,
        "passed": not issues,
        "durationMs": round((perf_counter() - started) * 1000),
        "issues": issues,
        "title": plan.title,
        "qualityScore": _latest_quality_score(trace),
        "fallbackUsed": bool(trace and trace.fallback_used),
        "ragBackend": _rag_backend(trace),
    }


def _run_http_case(base_url: str, user_id: str, case: EvalCase) -> dict[str, Any]:
    started = perf_counter()
    issues: list[str] = []
    plan: dict[str, Any] = {}
    trace: dict[str, Any] | None = None
    try:
        payload = case.request.model_dump(mode="json", by_alias=True)
        plan = _http_json(
            f"{base_url}/api/v1/trip-plan",
            method="POST",
            payload=payload,
            headers={"X-User-Id": user_id},
        )
        status = _http_json(f"{base_url}/api/v1/agent/status")
        trace = status.get("lastRunTrace") if isinstance(status.get("lastRunTrace"), dict) else None
    except Exception as exc:
        issues.append(f"http_error:{exc.__class__.__name__}")

    days = plan.get("days") or []
    if len(days) != case.request.days:
        issues.append("day_count_mismatch")
    if [day.get("day") for day in days] != list(range(1, case.request.days + 1)):
        issues.append("day_numbers_not_sequential")
    if not all(day.get("attractions") for day in days):
        issues.append("missing_attractions")
    if not all(day.get("routes") for day in days):
        issues.append("missing_routes")
    if not plan.get("weatherInfo"):
        issues.append("missing_weather")
    budget = plan.get("budget") or {}
    if int(budget.get("total") or 0) <= 0:
        issues.append("missing_budget")
    if "Research" not in str(plan.get("overallSuggestions") or ""):
        issues.append("missing_research_notes_in_plan")
    if trace is None:
        issues.append("missing_trace")
    else:
        completed = set(trace.get("completedNodes") or [])
        for node in ("trip_context", "retrieve_knowledge", "research_agent", "route_budget", "planner_agent", "trip_validation"):
            if node not in completed:
                issues.append(f"missing_node:{node}")
        events = trace.get("nodeEvents") or []
        quality_event = next((event for event in events if event.get("nodeName") == "trip_validation"), None)
        if quality_event is None or quality_event.get("score") is None or not quality_event.get("grade"):
            issues.append("missing_quality_score")
        if _rag_backend_from_trace_dict(trace) in {"missing", "unknown"}:
            issues.append("missing_rag_backend")

    return {
        "name": case.name,
        "mode": "http",
        "passed": not issues,
        "durationMs": round((perf_counter() - started) * 1000),
        "issues": issues,
        "title": plan.get("title", ""),
        "qualityScore": _latest_quality_score_from_trace_dict(trace),
        "fallbackUsed": bool(trace and trace.get("fallbackUsed")),
        "ragBackend": _rag_backend_from_trace_dict(trace),
    }


def _http_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} returned {exc.code}: {detail[:400]}") from exc


def _latest_quality_score(trace: Any) -> int | None:
    if trace is None:
        return None
    event = next((item for item in trace.node_events if item.node_name == "trip_validation"), None)
    return event.score if event else None


def _rag_backend(trace: Any) -> str:
    if trace is None:
        return "missing"
    event = next((item for item in trace.node_events if item.node_name == "retrieve_knowledge"), None)
    if event is None:
        return "missing"
    detail = event.detail or ""
    prefix = "backend="
    if detail.startswith(prefix):
        return detail[len(prefix):].split(";", 1)[0]
    return "unknown"


def _latest_quality_score_from_trace_dict(trace: dict[str, Any] | None) -> int | None:
    if trace is None:
        return None
    event = next((item for item in trace.get("nodeEvents") or [] if item.get("nodeName") == "trip_validation"), None)
    score = event.get("score") if event else None
    return int(score) if score is not None else None


def _rag_backend_from_trace_dict(trace: dict[str, Any] | None) -> str:
    if trace is None:
        return "missing"
    event = next((item for item in trace.get("nodeEvents") or [] if item.get("nodeName") == "retrieve_knowledge"), None)
    if event is None:
        return "missing"
    detail = str(event.get("detail") or "")
    prefix = "backend="
    if detail.startswith(prefix):
        return detail[len(prefix):].split(";", 1)[0]
    return "unknown"


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


def _selected_cases(case_names: list[str] | None, case_limit: int) -> list[EvalCase]:
    cases = _cases()
    if case_names:
        wanted = set(case_names)
        cases = [case for case in cases if case.name in wanted]
        missing = wanted.difference(case.name for case in cases)
        if missing:
            raise SystemExit(f"Unknown eval case(s): {', '.join(sorted(missing))}")
    if case_limit > 0:
        cases = cases[:case_limit]
    if not cases:
        raise SystemExit("No eval cases selected")
    return cases


if __name__ == "__main__":
    raise SystemExit(main())
