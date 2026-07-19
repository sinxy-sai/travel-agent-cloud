from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Callable, Generic, TypedDict, TypeVar, cast
from uuid import uuid4

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - exercised when optional dependency is absent.
    END = None
    START = None
    StateGraph = None

from app.agent_engines.tool_tracing import TracingTravelToolProvider
from app.agent_engines.langchain_nodes import LangChainTravelAgentNodeRunner
from app.agent_engines.types import (
    TravelAgentEngineCapabilities,
    TravelAgentNodeEvent,
    TravelAgentRunTrace,
    TravelAgentToolCall,
)
from app.llm import LLMClient
from app.knowledge import KnowledgeRetrievalResult, KnowledgeRetriever, create_knowledge_retriever
from app.plan_quality import TripPlanQualityReport
from app.planning_context import TravelPlanningContext, build_travel_planning_context
from app.planner import (
    build_mock_regenerated_trip_day,
    build_mock_revised_trip_plan,
    build_mock_trip_plan,
    enrich_trip_plan_response,
    trip_plan_request_from_saved,
)
from app.progress import notify_trip_plan_progress
from app.schemas import (
    AgentMode,
    Attraction,
    Budget,
    ChatMessage,
    ChatRequest,
    Hotel,
    KnowledgeRecordCreateRequest,
    Meal,
    RouteLeg,
    SavedTripPlan,
    TripDay,
    TripPlanRequest,
    TripPlanResponse,
    WeatherInfo,
)
from app.settings import Settings
from app.skills.itinerary_composition.executor import compose_trip_plan
from app.skills.plan_quality.executor import run_plan_quality
from app.skills.route_budget.executor import run_route_budget
from app.skills.schemas import ResearchNote, SkillTrace
from app.skills.travel_research.executor import run_travel_research
from app.travel_tools import TravelToolProvider

MAX_TRACE_HISTORY = 10
WorkflowStateT = TypeVar("WorkflowStateT")


class _GraphWorkflowState(TypedDict):
    state: object
    completed_nodes: list[str]


@dataclass
class ChatWorkflowState:
    request: ChatRequest
    messages: list[ChatMessage]
    response: str | None = None
    fallback_used: bool = False


@dataclass
class TripPlanningWorkflowState:
    request: TripPlanRequest
    planning_context: TravelPlanningContext | None = None
    draft_plan: TripPlanResponse | None = None
    attractions_by_day: dict[int, list[Attraction]] = field(default_factory=dict)
    weather_info: list[WeatherInfo] = field(default_factory=list)
    hotels_by_day: dict[int, Hotel] = field(default_factory=dict)
    meals_by_day: dict[int, list[Meal]] = field(default_factory=dict)
    research_notes: tuple[ResearchNote, ...] = ()
    routes_by_day: dict[int, list[RouteLeg]] = field(default_factory=dict)
    budget: Budget | None = None
    knowledge_result: KnowledgeRetrievalResult | None = None
    research_trace: SkillTrace | None = None
    route_budget_trace: SkillTrace | None = None
    final_plan: TripPlanResponse | None = None
    quality_report: TripPlanQualityReport | None = None
    quality_revision_count: int = 0
    fallback_used: bool = False


@dataclass
class DayRegenerationWorkflowState:
    saved_trip_plan: SavedTripPlan
    day: int
    instruction: str
    regenerated_day: TripDay | None = None
    fallback_used: bool = False


@dataclass
class TripRevisionWorkflowState:
    saved_trip_plan: SavedTripPlan
    instruction: str
    request: TripPlanRequest | None = None
    planning_context: TravelPlanningContext | None = None
    draft_plan: TripPlanResponse | None = None
    final_plan: TripPlanResponse | None = None
    quality_report: TripPlanQualityReport | None = None
    fallback_used: bool = False


@dataclass(frozen=True)
class WorkflowRunResult(Generic[WorkflowStateT]):
    state: WorkflowStateT
    completed_nodes: tuple[str, ...]


class LangGraphTravelAgentEngine:
    """Graph-shaped engine with a small internal runner.

    The public contract is already shaped as graph nodes. When the optional
    LangGraph dependency is installed, the node chain is executed by a compiled
    StateGraph. Local development can still run through the internal fallback
    runner when that dependency is not installed.
    """

    name = "langgraph:workflow-runner"

    def __init__(self, settings: Settings, travel_tools: TravelToolProvider) -> None:
        self._settings = settings
        self._llm_client = LLMClient(settings)
        self._langchain_node_runner = LangChainTravelAgentNodeRunner(settings)
        self._knowledge_retriever = create_knowledge_retriever(settings)
        self._travel_tools = travel_tools
        self._langgraph_available = StateGraph is not None
        self._last_run_trace: TravelAgentRunTrace | None = None
        self._recent_run_traces: list[TravelAgentRunTrace] = []

    @property
    def llm_enabled(self) -> bool:
        return self._llm_client.enabled

    @property
    def capabilities(self) -> TravelAgentEngineCapabilities:
        return TravelAgentEngineCapabilities(
            supports_chat=True,
            supports_trip_planning=True,
            supports_day_regeneration=True,
            supports_trip_revision=True,
            workflow_nodes=(
                "chat_llm",
                "chat_fallback",
                "trip_context",
                "retrieve_knowledge",
                "trip_draft",
                "research_agent",
                "route_budget",
                "planner_agent",
                "trip_revision",
                "trip_validation",
                "day_regeneration",
                "day_fallback",
            ),
            dependency_mode=_dependency_mode(self._langgraph_available, self._langchain_node_runner.enabled),
        )

    @property
    def last_run_trace(self) -> TravelAgentRunTrace | None:
        return self._last_run_trace

    @property
    def recent_run_traces(self) -> tuple[TravelAgentRunTrace, ...]:
        return tuple(self._recent_run_traces)

    @property
    def knowledge_backend(self) -> str:
        return self._knowledge_retriever.backend

    def list_knowledge_records(self, destination: str | None = None, limit: int = 20) -> tuple[dict[str, object], ...]:
        return tuple(record.to_dict() for record in self._knowledge_retriever.list_records(destination, limit))

    def seed_destination_knowledge(self, destination: str) -> int:
        return self._knowledge_retriever.seed_destination_knowledge(destination)

    def create_knowledge_record(self, request: KnowledgeRecordCreateRequest) -> dict[str, object]:
        return self._knowledge_retriever.create_record(request).to_dict()

    def delete_knowledge_record(self, record_id: str) -> bool:
        return self._knowledge_retriever.delete_record(record_id)

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        started_at = _utc_timestamp()
        started = perf_counter()
        state = ChatWorkflowState(request=request, messages=messages)
        workflow = self._run_workflow(state, (
            ("chat_llm", self._chat_llm_node),
            ("chat_fallback", self._chat_fallback_node),
        ))
        state = workflow.state
        response = state.response or _build_rule_based_reply(request)
        self._record_trace(self._build_trace(
            operation="chat",
            completed_nodes=workflow.completed_nodes,
            fallback_used=state.fallback_used,
            node_events=_chat_node_events(state),
            tool_calls=(),
            started_at=started_at,
            duration_ms=_elapsed_ms(started),
        ))
        return response

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        started_at = _utc_timestamp()
        started = perf_counter()
        tool_calls: list[TravelAgentToolCall] = []
        traced_tools = TracingTravelToolProvider(self._travel_tools, tool_calls)
        state = TripPlanningWorkflowState(request=request)
        workflow = self._run_workflow(state, (
            ("trip_context", self._trip_context_node),
            ("retrieve_knowledge", self._retrieve_knowledge_node),
            ("trip_draft", self._trip_draft_node),
            ("research_agent", lambda current: self._research_agent_node(current, traced_tools)),
            ("route_budget", lambda current: self._route_budget_node(current, traced_tools)),
            ("planner_agent", self._planner_agent_node),
            ("trip_validation", lambda current: self._trip_validation_node(current, traced_tools)),
        ))
        state = workflow.state
        response = state.final_plan or build_mock_trip_plan(request, traced_tools, state.planning_context)
        try:
            self._knowledge_retriever.remember_successful_plan(request, response)
        except Exception:
            pass
        self._record_trace(self._build_trace(
            operation="trip_plan",
            completed_nodes=workflow.completed_nodes,
            fallback_used=state.fallback_used,
            node_events=_trip_node_events(state),
            tool_calls=tuple(tool_calls),
            started_at=started_at,
            duration_ms=_elapsed_ms(started),
        ))
        return response

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        started_at = _utc_timestamp()
        started = perf_counter()
        state = DayRegenerationWorkflowState(
            saved_trip_plan=saved_trip_plan,
            day=day,
            instruction=instruction,
        )
        workflow = self._run_workflow(state, (
            ("day_regeneration", self._day_regeneration_node),
            ("day_fallback", self._day_fallback_node),
        ))
        state = workflow.state
        response = state.regenerated_day or build_mock_regenerated_trip_day(saved_trip_plan, day, instruction)
        self._record_trace(self._build_trace(
            operation="day_regeneration",
            completed_nodes=workflow.completed_nodes,
            fallback_used=state.fallback_used,
            node_events=_day_node_events(state),
            tool_calls=(),
            started_at=started_at,
            duration_ms=_elapsed_ms(started),
        ))
        return response

    def revise_trip_plan(self, saved_trip_plan: SavedTripPlan, instruction: str) -> TripPlanResponse:
        started_at = _utc_timestamp()
        started = perf_counter()
        tool_calls: list[TravelAgentToolCall] = []
        traced_tools = TracingTravelToolProvider(self._travel_tools, tool_calls)
        state = TripRevisionWorkflowState(saved_trip_plan=saved_trip_plan, instruction=instruction)
        workflow = self._run_workflow(state, (
            ("trip_context", self._revision_context_node),
            ("trip_revision", self._revision_draft_node),
            ("trip_enrichment", lambda current: self._revision_enrichment_node(current, traced_tools)),
            ("trip_validation", lambda current: self._revision_validation_node(current, traced_tools)),
        ))
        state = workflow.state
        response = state.final_plan or build_mock_revised_trip_plan(saved_trip_plan, instruction)
        self._record_trace(self._build_trace(
            operation="trip_revision",
            completed_nodes=workflow.completed_nodes,
            fallback_used=state.fallback_used,
            node_events=_revision_node_events(state),
            tool_calls=tuple(tool_calls),
            started_at=started_at,
            duration_ms=_elapsed_ms(started),
        ))
        return response

    def _run_workflow(
        self,
        initial_state: WorkflowStateT,
        nodes: tuple[tuple[str, Callable[[WorkflowStateT], WorkflowStateT]], ...],
    ) -> WorkflowRunResult[WorkflowStateT]:
        if self._langgraph_available:
            return self._run_compiled_langgraph_workflow(initial_state, nodes)
        return self._run_internal_workflow(initial_state, nodes)

    def _run_internal_workflow(
        self,
        initial_state: WorkflowStateT,
        nodes: tuple[tuple[str, Callable[[WorkflowStateT], WorkflowStateT]], ...],
    ) -> WorkflowRunResult[WorkflowStateT]:
        state = initial_state
        completed_nodes: list[str] = []
        for node_name, node in nodes:
            state = node(state)
            completed_nodes.append(node_name)
        return WorkflowRunResult(state=state, completed_nodes=tuple(completed_nodes))

    def _run_compiled_langgraph_workflow(
        self,
        initial_state: WorkflowStateT,
        nodes: tuple[tuple[str, Callable[[WorkflowStateT], WorkflowStateT]], ...],
    ) -> WorkflowRunResult[WorkflowStateT]:
        if StateGraph is None or START is None or END is None:
            return self._run_internal_workflow(initial_state, nodes)

        workflow = StateGraph(_GraphWorkflowState)

        for node_name, node in nodes:
            workflow.add_node(node_name, _wrap_workflow_node(node_name, node))

        first_node_name = nodes[0][0]
        workflow.add_edge(START, first_node_name)
        for index, (node_name, _node) in enumerate(nodes):
            next_node_name = nodes[index + 1][0] if index + 1 < len(nodes) else END
            workflow.add_edge(node_name, next_node_name)

        compiled = workflow.compile()
        result = compiled.invoke({"state": initial_state, "completed_nodes": []})
        return WorkflowRunResult(
            state=cast(WorkflowStateT, result["state"]),
            completed_nodes=tuple(result["completed_nodes"]),
        )

    def _revision_context_node(self, state: TripRevisionWorkflowState) -> TripRevisionWorkflowState:
        request = trip_plan_request_from_saved(state.saved_trip_plan, state.instruction)
        return TripRevisionWorkflowState(
            saved_trip_plan=state.saved_trip_plan,
            instruction=state.instruction,
            request=request,
            planning_context=build_travel_planning_context(request),
            draft_plan=state.draft_plan,
            final_plan=state.final_plan,
            quality_report=state.quality_report,
            fallback_used=state.fallback_used,
        )

    def _revision_draft_node(self, state: TripRevisionWorkflowState) -> TripRevisionWorkflowState:
        draft_plan = self._llm_client.revise_trip_plan(state.saved_trip_plan, state.instruction)
        return TripRevisionWorkflowState(
            saved_trip_plan=state.saved_trip_plan,
            instruction=state.instruction,
            request=state.request,
            planning_context=state.planning_context,
            draft_plan=draft_plan,
            final_plan=state.final_plan,
            quality_report=state.quality_report,
            fallback_used=state.fallback_used or draft_plan is None,
        )

    def _revision_enrichment_node(
        self,
        state: TripRevisionWorkflowState,
        travel_tools: TravelToolProvider,
    ) -> TripRevisionWorkflowState:
        if state.request is None or state.planning_context is None:
            return state
        candidate_plan = state.draft_plan or build_mock_revised_trip_plan(state.saved_trip_plan, state.instruction)
        final_plan = (
            enrich_trip_plan_response(candidate_plan, state.request, travel_tools, state.planning_context)
            if state.draft_plan is not None
            else candidate_plan
        )
        return TripRevisionWorkflowState(
            saved_trip_plan=state.saved_trip_plan,
            instruction=state.instruction,
            request=state.request,
            planning_context=state.planning_context,
            draft_plan=state.draft_plan,
            final_plan=final_plan,
            quality_report=state.quality_report,
            fallback_used=state.fallback_used,
        )

    def _revision_validation_node(
        self,
        state: TripRevisionWorkflowState,
        travel_tools: TravelToolProvider,
    ) -> TripRevisionWorkflowState:
        if state.request is None or state.planning_context is None:
            return state
        candidate_plan = state.final_plan or build_mock_revised_trip_plan(state.saved_trip_plan, state.instruction)
        final_plan, quality_report = run_plan_quality(
            candidate_plan,
            state.request,
            travel_tools,
            state.planning_context,
        )
        return TripRevisionWorkflowState(
            saved_trip_plan=state.saved_trip_plan,
            instruction=state.instruction,
            request=state.request,
            planning_context=state.planning_context,
            draft_plan=state.draft_plan,
            final_plan=final_plan,
            quality_report=quality_report,
            fallback_used=state.fallback_used or quality_report.repaired,
        )

    def _chat_llm_node(self, state: ChatWorkflowState) -> ChatWorkflowState:
        response = self._llm_client.generate_chat_reply(state.messages, state.request.mode)
        return ChatWorkflowState(request=state.request, messages=state.messages, response=response)

    def _chat_fallback_node(self, state: ChatWorkflowState) -> ChatWorkflowState:
        if state.response:
            return state
        return ChatWorkflowState(
            request=state.request,
            messages=state.messages,
            response=_build_rule_based_reply(state.request),
            fallback_used=True,
        )

    def _trip_context_node(self, state: TripPlanningWorkflowState) -> TripPlanningWorkflowState:
        notify_trip_plan_progress("understanding")
        return TripPlanningWorkflowState(
            request=state.request,
            planning_context=build_travel_planning_context(state.request),
            draft_plan=state.draft_plan,
            attractions_by_day=state.attractions_by_day,
            weather_info=state.weather_info,
            hotels_by_day=state.hotels_by_day,
            meals_by_day=state.meals_by_day,
            research_notes=state.research_notes,
            routes_by_day=state.routes_by_day,
            budget=state.budget,
            knowledge_result=state.knowledge_result,
            research_trace=state.research_trace,
            route_budget_trace=state.route_budget_trace,
            final_plan=state.final_plan,
            quality_report=state.quality_report,
            quality_revision_count=state.quality_revision_count,
            fallback_used=state.fallback_used,
        )

    def _retrieve_knowledge_node(self, state: TripPlanningWorkflowState) -> TripPlanningWorkflowState:
        if state.planning_context is None:
            return state
        knowledge_result = self._knowledge_retriever.retrieve(state.request, state.planning_context)
        return _copy_trip_state(
            state,
            planning_context=state.planning_context.with_retrieved_knowledge(knowledge_result.hits),
            knowledge_result=knowledge_result,
        )

    def _trip_draft_node(self, state: TripPlanningWorkflowState) -> TripPlanningWorkflowState:
        notify_trip_plan_progress("finding_attractions")
        draft_plan = self._llm_client.generate_trip_plan(state.request, state.planning_context)
        return TripPlanningWorkflowState(
            request=state.request,
            planning_context=state.planning_context,
            draft_plan=draft_plan,
            attractions_by_day=state.attractions_by_day,
            weather_info=state.weather_info,
            hotels_by_day=state.hotels_by_day,
            meals_by_day=state.meals_by_day,
            research_notes=state.research_notes,
            routes_by_day=state.routes_by_day,
            budget=state.budget,
            knowledge_result=state.knowledge_result,
            research_trace=state.research_trace,
            route_budget_trace=state.route_budget_trace,
            quality_report=state.quality_report,
            quality_revision_count=state.quality_revision_count,
            fallback_used=state.fallback_used or draft_plan is None,
        )

    def _research_agent_node(
        self,
        state: TripPlanningWorkflowState,
        travel_tools: TravelToolProvider,
    ) -> TripPlanningWorkflowState:
        notify_trip_plan_progress("finding_attractions")
        notify_trip_plan_progress("checking_weather")
        notify_trip_plan_progress("selecting_stays_meals")
        research = run_travel_research(
            state.request,
            travel_tools,
            self._langchain_node_runner,
            self._settings,
            state.planning_context,
        )
        return _copy_trip_state(
            state,
            attractions_by_day=research.attractions_by_day,
            weather_info=research.weather_info,
            hotels_by_day=research.hotels_by_day,
            meals_by_day=research.meals_by_day,
            research_notes=research.research_notes,
            research_trace=research.trace,
        )

    def _route_budget_node(
        self,
        state: TripPlanningWorkflowState,
        travel_tools: TravelToolProvider,
    ) -> TripPlanningWorkflowState:
        notify_trip_plan_progress("building_routes_budget")
        route_budget = run_route_budget(
            state.request,
            state.attractions_by_day,
            state.hotels_by_day,
            travel_tools,
            self._langchain_node_runner,
            state.planning_context,
        )
        return _copy_trip_state(
            state,
            routes_by_day=route_budget.routes_by_day,
            budget=route_budget.budget,
            route_budget_trace=route_budget.trace,
        )

    def _planner_agent_node(self, state: TripPlanningWorkflowState) -> TripPlanningWorkflowState:
        composed_plan = compose_trip_plan(
            request=state.request,
            planning_context=state.planning_context,
            draft_plan=state.draft_plan,
            attractions_by_day=state.attractions_by_day,
            weather_info=state.weather_info,
            hotels_by_day=state.hotels_by_day,
            meals_by_day=state.meals_by_day,
            research_notes=state.research_notes,
            routes_by_day=state.routes_by_day,
            budget=state.budget,
        )
        llm_plan = (
            self._llm_client.generate_trip_plan_from_research(
                state.request,
                state.planning_context,
                composed_plan,
                state.research_notes,
            )
            if state.planning_context is not None
            else None
        )
        final_plan = llm_plan or composed_plan
        return TripPlanningWorkflowState(
            request=state.request,
            planning_context=state.planning_context,
            draft_plan=state.draft_plan,
            attractions_by_day=state.attractions_by_day,
            weather_info=state.weather_info,
            hotels_by_day=state.hotels_by_day,
            meals_by_day=state.meals_by_day,
            research_notes=state.research_notes,
            routes_by_day=state.routes_by_day,
            budget=state.budget,
            knowledge_result=state.knowledge_result,
            research_trace=state.research_trace,
            route_budget_trace=state.route_budget_trace,
            final_plan=final_plan,
            quality_report=state.quality_report,
            quality_revision_count=state.quality_revision_count,
            fallback_used=state.fallback_used,
        )

    def _trip_validation_node(
        self,
        state: TripPlanningWorkflowState,
        travel_tools: TravelToolProvider,
    ) -> TripPlanningWorkflowState:
        notify_trip_plan_progress("quality_checking")
        fallback_used = state.fallback_used
        candidate_plan = state.final_plan
        if candidate_plan is None or not candidate_plan.days:
            candidate_plan = build_mock_trip_plan(state.request, travel_tools, state.planning_context)
            fallback_used = True

        final_plan, quality_report, quality_revision_count = _run_bounded_quality_loop(
            candidate_plan,
            state.request,
            travel_tools,
            state.planning_context,
        )
        notify_trip_plan_progress("quality_checking")
        return TripPlanningWorkflowState(
            request=state.request,
            planning_context=state.planning_context,
            draft_plan=state.draft_plan,
            attractions_by_day=state.attractions_by_day,
            weather_info=state.weather_info,
            hotels_by_day=state.hotels_by_day,
            meals_by_day=state.meals_by_day,
            research_notes=state.research_notes,
            routes_by_day=state.routes_by_day,
            budget=state.budget,
            knowledge_result=state.knowledge_result,
            research_trace=state.research_trace,
            route_budget_trace=state.route_budget_trace,
            final_plan=final_plan,
            quality_report=quality_report,
            quality_revision_count=quality_revision_count,
            fallback_used=fallback_used or quality_revision_count > 0,
        )

    def _day_regeneration_node(self, state: DayRegenerationWorkflowState) -> DayRegenerationWorkflowState:
        regenerated_day = self._llm_client.regenerate_trip_day(
            state.saved_trip_plan,
            state.day,
            state.instruction,
        )
        return DayRegenerationWorkflowState(
            saved_trip_plan=state.saved_trip_plan,
            day=state.day,
            instruction=state.instruction,
            regenerated_day=regenerated_day,
        )

    def _day_fallback_node(self, state: DayRegenerationWorkflowState) -> DayRegenerationWorkflowState:
        if state.regenerated_day:
            return state
        return DayRegenerationWorkflowState(
            saved_trip_plan=state.saved_trip_plan,
            day=state.day,
            instruction=state.instruction,
            regenerated_day=build_mock_regenerated_trip_day(
                state.saved_trip_plan,
                state.day,
                state.instruction,
            ),
            fallback_used=True,
        )

    def _record_trace(self, trace: TravelAgentRunTrace) -> None:
        self._last_run_trace = trace
        self._recent_run_traces.insert(0, trace)
        del self._recent_run_traces[MAX_TRACE_HISTORY:]

    def _build_trace(
        self,
        operation: str,
        completed_nodes: tuple[str, ...],
        fallback_used: bool,
        node_events: tuple[TravelAgentNodeEvent, ...],
        tool_calls: tuple[TravelAgentToolCall, ...],
        started_at: str,
        duration_ms: int,
    ) -> TravelAgentRunTrace:
        return TravelAgentRunTrace(
            run_id=str(uuid4()),
            operation=operation,
            engine_name=self.name,
            started_at=started_at,
            duration_ms=duration_ms,
            workflow_nodes=self.capabilities.workflow_nodes,
            completed_nodes=completed_nodes,
            fallback_used=fallback_used,
            llm_enabled=self.llm_enabled,
            node_events=node_events,
            tool_calls=tool_calls,
        )


def _build_rule_based_reply(request: ChatRequest) -> str:
    message = request.message.strip()
    if request.mode == AgentMode.TRIP_PLANNING:
        return (
            "I can turn this travel requirement into a structured itinerary. "
            f"Current request: {message}. "
            "Next I will collect destination, days, budget, interests, and constraints before calling trip planning tools."
        )

    return (
        "I received your travel question and created a conversation context. "
        f"You said: {message}. "
        "The current runtime is rule-based; LLM planning and tool calls will be added behind this contract."
    )


def _dependency_mode(langgraph_available: bool, langchain_available: bool) -> str:
    graph_mode = "compiled-langgraph" if langgraph_available else "internal-graph-runner"
    if langchain_available:
        return f"{graph_mode}+langchain-tool-calling"
    return graph_mode


def _copy_trip_state(state: TripPlanningWorkflowState, **updates: object) -> TripPlanningWorkflowState:
    payload = {
        "request": state.request,
        "planning_context": state.planning_context,
        "draft_plan": state.draft_plan,
        "attractions_by_day": state.attractions_by_day,
        "weather_info": state.weather_info,
        "hotels_by_day": state.hotels_by_day,
        "meals_by_day": state.meals_by_day,
        "research_notes": state.research_notes,
        "routes_by_day": state.routes_by_day,
        "budget": state.budget,
        "knowledge_result": state.knowledge_result,
        "research_trace": state.research_trace,
        "route_budget_trace": state.route_budget_trace,
        "final_plan": state.final_plan,
        "quality_report": state.quality_report,
        "quality_revision_count": state.quality_revision_count,
        "fallback_used": state.fallback_used,
    }
    payload.update(updates)
    return TripPlanningWorkflowState(**payload)


def _run_bounded_quality_loop(
    candidate_plan: TripPlanResponse,
    request: TripPlanRequest,
    travel_tools: TravelToolProvider,
    planning_context: TravelPlanningContext | None,
) -> tuple[TripPlanResponse, TripPlanQualityReport, int]:
    current_plan = candidate_plan
    revision_count = 0
    final_report: TripPlanQualityReport | None = None

    current_plan, first_report = run_plan_quality(current_plan, request, travel_tools, planning_context)
    final_report = first_report
    if not first_report.passed and first_report.repaired:
        revision_count = 1
        current_plan, final_report = run_plan_quality(current_plan, request, travel_tools, planning_context)

    if final_report is None:
        current_plan, final_report = run_plan_quality(current_plan, request, travel_tools, planning_context)
    return current_plan, final_report, revision_count


def _wrap_workflow_node(
    node_name: str,
    node: Callable[[WorkflowStateT], WorkflowStateT],
) -> Callable[[_GraphWorkflowState], _GraphWorkflowState]:
    def wrapped(graph_state: _GraphWorkflowState) -> _GraphWorkflowState:
        next_state = node(cast(WorkflowStateT, graph_state["state"]))
        return {
            "state": next_state,
            "completed_nodes": [*graph_state["completed_nodes"], node_name],
        }

    return wrapped


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _chat_node_events(state: ChatWorkflowState) -> tuple[TravelAgentNodeEvent, ...]:
    llm_event = (
        _node_event("chat_llm", "SKIPPED", "llm_disabled_or_empty_response")
        if state.fallback_used
        else _node_event("chat_llm", "SUCCEEDED", "chat_reply_generated")
    )
    fallback_event = (
        _node_event("chat_fallback", "FALLBACK", "rule_based_reply")
        if state.fallback_used
        else _node_event("chat_fallback", "SKIPPED", "llm_response_available")
    )
    return (llm_event, fallback_event)


def _trip_node_events(state: TripPlanningWorkflowState) -> tuple[TravelAgentNodeEvent, ...]:
    context_event = (
        _node_event("trip_context", "SUCCEEDED", state.planning_context.to_trace_detail())
        if state.planning_context is not None
        else _node_event("trip_context", "FAILED", "planning_context_missing")
    )
    draft_event = (
        _node_event("trip_draft", "SKIPPED", "llm_disabled_or_invalid_response")
        if state.draft_plan is None
        else _node_event("trip_draft", "SUCCEEDED", "draft_plan_generated")
    )
    knowledge_event = (
        _node_event("retrieve_knowledge", "SUCCEEDED", state.knowledge_result.to_trace_detail())
        if state.knowledge_result is not None
        else _node_event("retrieve_knowledge", "SKIPPED", "knowledge_not_available")
    )
    research_event = (
        _node_event("research_agent", "SUCCEEDED", state.research_trace.to_detail())
        if state.research_trace is not None and state.research_trace.status == "success"
        else _node_event(
            "research_agent",
            "FALLBACK" if state.research_trace is not None else "FAILED",
            state.research_trace.to_detail() if state.research_trace is not None else "research_bundle_missing",
        )
    )
    route_budget_event = (
        _node_event("route_budget", "SUCCEEDED", state.route_budget_trace.to_detail())
        if state.route_budget_trace is not None and state.route_budget_trace.status == "success"
        else _node_event(
            "route_budget",
            "FALLBACK" if state.route_budget_trace is not None else "FAILED",
            state.route_budget_trace.to_detail() if state.route_budget_trace is not None else "route_budget_missing",
        )
    )
    planner_event = (
        _node_event("planner_agent", "SUCCEEDED", "itinerary_assembled_from_agent_outputs")
        if state.final_plan is not None
        else _node_event("planner_agent", "FAILED", "final_plan_missing")
    )
    validation_event = (
        _node_event(
            "trip_validation",
            "FALLBACK" if state.quality_revision_count > 0 else "SUCCEEDED",
            (
                f"{state.quality_report.to_trace_detail()}; revisions={state.quality_revision_count}"
                if state.quality_report
                else "quality_report_missing"
            ),
            score=state.quality_report.score if state.quality_report else None,
            grade=state.quality_report.grade if state.quality_report else None,
        )
    )
    return (
        context_event,
        knowledge_event,
        draft_event,
        research_event,
        route_budget_event,
        planner_event,
        validation_event,
    )


def _day_node_events(state: DayRegenerationWorkflowState) -> tuple[TravelAgentNodeEvent, ...]:
    generation_event = (
        _node_event("day_regeneration", "SKIPPED", "llm_disabled_or_invalid_response")
        if state.fallback_used
        else _node_event("day_regeneration", "SUCCEEDED", "day_json_generated")
    )
    fallback_event = (
        _node_event("day_fallback", "FALLBACK", "mock_day_generated")
        if state.fallback_used
        else _node_event("day_fallback", "SKIPPED", "llm_day_available")
    )
    return (generation_event, fallback_event)


def _revision_node_events(state: TripRevisionWorkflowState) -> tuple[TravelAgentNodeEvent, ...]:
    context_event = (
        _node_event("trip_context", "SUCCEEDED", state.planning_context.to_trace_detail())
        if state.planning_context is not None
        else _node_event("trip_context", "FAILED", "planning_context_missing")
    )
    revision_event = (
        _node_event("trip_revision", "FALLBACK", "mock_trip_revision_generated")
        if state.draft_plan is None
        else _node_event("trip_revision", "SUCCEEDED", "trip_revision_json_generated")
    )
    enrichment_event = (
        _node_event("trip_enrichment", "SKIPPED", "mock_revision_already_enriched")
        if state.draft_plan is None
        else _node_event("trip_enrichment", "SUCCEEDED", "travel_tools_applied")
    )
    validation_event = _node_event(
        "trip_validation",
        "FALLBACK" if state.quality_report and state.quality_report.repaired else "SUCCEEDED",
        state.quality_report.to_trace_detail() if state.quality_report else "quality_report_missing",
        score=state.quality_report.score if state.quality_report else None,
        grade=state.quality_report.grade if state.quality_report else None,
    )
    return (context_event, revision_event, enrichment_event, validation_event)


def _node_event(
    node_name: str,
    status: str,
    detail: str,
    *,
    score: int | None = None,
    grade: str | None = None,
) -> TravelAgentNodeEvent:
    return TravelAgentNodeEvent(node_name=node_name, status=status, detail=detail, score=score, grade=grade)


def _agent_node_event(node_name: str, succeeded: bool, detail: str) -> TravelAgentNodeEvent:
    return _node_event(node_name, "SUCCEEDED" if succeeded else "FAILED", detail)
