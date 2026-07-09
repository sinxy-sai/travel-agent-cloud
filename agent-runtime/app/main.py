from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.agent import handle_chat
from app.conversations import (
    ConversationNotFoundError,
    ConversationStore,
    DatabaseConversationStore,
    TripPlanNotFoundError,
)
from app.db import maybe_create_session_factory
from app.exporter import saved_trip_plan_to_markdown
from app.llm import LLMClient
from app.planner import build_mock_trip_plan
from app.schemas import (
    ChatRequest,
    ChatResponse,
    Conversation,
    ConversationListResponse,
    MessageRole,
    SavedTripPlan,
    TripPlanListResponse,
    TripPlanRequest,
    TripPlanResponse,
)
from app.settings import get_settings
from app.users import get_user_id

settings = get_settings()
session_factory = maybe_create_session_factory(settings)
conversation_store = DatabaseConversationStore(session_factory) if session_factory else ConversationStore()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "llmEnabled": LLMClient(settings).enabled,
        "databaseEnabled": session_factory is not None,
    }


@app.post("/api/v1/trip-plan", response_model=TripPlanResponse)
def create_trip_plan(request: TripPlanRequest, user_id: str = Depends(get_user_id)) -> TripPlanResponse:
    response = LLMClient(settings).generate_trip_plan(request) or build_mock_trip_plan(request)
    conversation = conversation_store.get_or_create(
        user_id=user_id,
        conversation_id=None,
        mode="TRIP_PLANNING",
        title=response.title,
    )
    conversation_store.append_message(
        conversation,
        MessageRole.USER,
        f"Plan {request.days} days in {request.destination}, budget={request.budget}, interests={request.interests}",
    )
    conversation_store.append_message(conversation, MessageRole.ASSISTANT, response.summary)
    conversation_store.save_trip_plan(user_id, conversation, request, response)
    return response


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user_id: str = Depends(get_user_id)) -> ChatResponse:
    try:
        return handle_chat(user_id, request, conversation_store, settings)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc


@app.get("/api/v1/conversations", response_model=ConversationListResponse)
def list_conversations(
    user_id: str = Depends(get_user_id),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
) -> ConversationListResponse:
    return conversation_store.list(user_id=user_id, page=page, page_size=page_size)


@app.get("/api/v1/conversations/{conversation_id}", response_model=Conversation)
def get_conversation(conversation_id: str, user_id: str = Depends(get_user_id)) -> Conversation:
    try:
        return conversation_store.get(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc


@app.get("/api/v1/trip-plans", response_model=TripPlanListResponse)
def list_trip_plans(
    user_id: str = Depends(get_user_id),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
) -> TripPlanListResponse:
    return conversation_store.list_trip_plans(user_id=user_id, page=page, page_size=page_size)


@app.get("/api/v1/trip-plans/{trip_plan_id}", response_model=SavedTripPlan)
def get_trip_plan(trip_plan_id: str, user_id: str = Depends(get_user_id)) -> SavedTripPlan:
    try:
        return conversation_store.get_trip_plan(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc


@app.get("/api/v1/trip-plans/{trip_plan_id}/export", response_class=PlainTextResponse)
def export_trip_plan(trip_plan_id: str, user_id: str = Depends(get_user_id)) -> PlainTextResponse:
    try:
        saved_trip_plan = conversation_store.get_trip_plan(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc

    filename = _download_filename(saved_trip_plan.title)
    return PlainTextResponse(
        content=saved_trip_plan_to_markdown(saved_trip_plan),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _download_filename(title: str) -> str:
    safe_title = "".join(character if character.isalnum() else "-" for character in title.lower())
    safe_title = "-".join(part for part in safe_title.split("-") if part)
    return f"{safe_title or 'trip-plan'}.md"
