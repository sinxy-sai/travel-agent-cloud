from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.agent import handle_chat
from app.auth import (
    AUTH_COOKIE_NAME,
    DatabaseUserStore,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    UserNotFoundError,
    UserStore,
    create_access_token,
    verify_access_token,
)
from app.conversations import (
    ConversationNotFoundError,
    ConversationStore,
    DatabaseConversationStore,
    TripPlanNotFoundError,
)
from app.db import maybe_create_session_factory
from app.events import CONVERSATION_SUMMARY_REQUESTED_EVENT, create_event_publisher
from app.exporter import saved_trip_plan_to_markdown
from app.llm import LLMClient
from app.observability import RequestLoggingMiddleware, configure_logging
from app.planner import build_mock_trip_plan
from app.profiles import DatabaseUserProfileStore, UserProfileStore
from app.schemas import (
    AuthAccountDeleteRequest,
    AuthLoginRequest,
    AuthPasswordChangeRequest,
    AuthRegisterRequest,
    AuthSession,
    AuthUser,
    AuthUserUpdateRequest,
    ChatRequest,
    ChatResponse,
    Conversation,
    ConversationListResponse,
    ConversationSummary,
    ConversationSummaryJob,
    ConversationUpdateRequest,
    MessageRole,
    SavedTripPlan,
    TripPlanListResponse,
    TripPlanRequest,
    TripPlanResponse,
    TripPlanUpdateRequest,
    UserDataExport,
    UserProfile,
    UserProfileUpdateRequest,
    to_camel,
)
from app.security import FixedWindowRateLimiter, SecurityHeadersMiddleware, client_identifier
from app.settings import get_settings
from app.summaries import (
    ConversationSummaryNotFoundError,
    ConversationSummaryStore,
    DatabaseConversationSummaryStore,
)
from app.summary_jobs import (
    ConversationSummaryJobNotFoundError,
    ConversationSummaryJobStore,
    DatabaseConversationSummaryJobStore,
)
from app.users import get_user_id
from app.workers.conversation_summarizer import ConversationSummarizerWorker, SummarizeConversationCommand

settings = get_settings()
configure_logging(settings)
session_factory = maybe_create_session_factory(settings)
conversation_store = DatabaseConversationStore(session_factory) if session_factory else ConversationStore()
profile_store = DatabaseUserProfileStore(session_factory) if session_factory else UserProfileStore()
summary_store = DatabaseConversationSummaryStore(session_factory) if session_factory else ConversationSummaryStore()
summary_job_store = (
    DatabaseConversationSummaryJobStore(session_factory) if session_factory else ConversationSummaryJobStore()
)
user_store = DatabaseUserStore(session_factory) if session_factory else UserStore()
event_publisher = create_event_publisher(settings)
conversation_summarizer = ConversationSummarizerWorker(conversation_store, summary_store, event_publisher)
auth_rate_limiter = FixedWindowRateLimiter(
    settings.auth_rate_limit_max_attempts,
    settings.auth_rate_limit_window_seconds,
)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
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
        "messageQueueEnabled": event_publisher.enabled,
    }


@app.post("/api/v1/auth/register", response_model=AuthSession, status_code=status.HTTP_201_CREATED)
def register(request: Request, payload: AuthRegisterRequest, response: Response) -> AuthSession:
    _check_auth_rate_limit(request, "register", payload.email)
    try:
        user = user_store.create_user(payload.email, payload.password, payload.display_name)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "EMAIL_ALREADY_REGISTERED", "message": "Email is already registered"},
        ) from exc
    token = create_access_token(settings, user.id)
    _set_auth_cookie(response, token)
    return AuthSession(user=user)


@app.post("/api/v1/auth/login", response_model=AuthSession)
def login(request: Request, payload: AuthLoginRequest, response: Response) -> AuthSession:
    _check_auth_rate_limit(request, "login", payload.email)
    try:
        user = user_store.authenticate(payload.email, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"},
        ) from exc
    token = create_access_token(settings, user.id)
    _set_auth_cookie(response, token)
    return AuthSession(user=user)


@app.get("/api/v1/auth/me", response_model=AuthUser)
def get_current_auth_user(request: Request) -> AuthUser:
    return _get_current_auth_user(request)


@app.patch("/api/v1/auth/me", response_model=AuthUser)
def update_current_auth_user(request: Request, payload: AuthUserUpdateRequest) -> AuthUser:
    user = _get_current_auth_user(request)
    try:
        return user_store.update_user(user.id, payload.display_name)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        ) from exc


@app.patch("/api/v1/auth/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(request: Request, payload: AuthPasswordChangeRequest) -> Response:
    user = _get_current_auth_user(request)
    _check_auth_rate_limit(request, "change-password", user.id)
    try:
        user_store.change_password(user.id, payload.current_password, payload.new_password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Current password is incorrect"},
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/v1/auth/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_auth_user(request: Request, payload: AuthAccountDeleteRequest, response: Response) -> Response:
    user = _get_current_auth_user(request)
    _check_auth_rate_limit(request, "delete-account", user.id)
    try:
        user_store.delete_user(user.id, payload.current_password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Current password is incorrect"},
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        ) from exc

    response.status_code = status.HTTP_204_NO_CONTENT
    _delete_auth_cookie(response)
    return response


@app.get("/api/v1/me/export", response_model=UserDataExport)
def export_current_user_data(request: Request) -> UserDataExport:
    user = _get_current_auth_user(request)
    conversations = _list_all_conversations(user.id)
    summaries = []
    for conversation in conversations:
        try:
            summaries.append(summary_store.get(user.id, conversation.id))
        except ConversationSummaryNotFoundError:
            continue

    return UserDataExport(
        exported_at=datetime.now(UTC),
        user=user,
        profile=profile_store.get(user.id),
        conversations=conversations,
        conversation_summaries=summaries,
        trip_plans=_list_all_trip_plans(user.id),
    )


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.status_code = status.HTTP_204_NO_CONTENT
    _delete_auth_cookie(response)
    return response


@app.post("/api/v1/trip-plan", response_model=TripPlanResponse)
def create_trip_plan(request: TripPlanRequest, user_id: str = Depends(get_user_id)) -> TripPlanResponse:
    response = LLMClient(settings).generate_trip_plan(request) or build_mock_trip_plan(request)
    try:
        conversation = conversation_store.get_or_create(
            user_id=user_id,
            conversation_id=request.conversation_id,
            mode="TRIP_PLANNING",
            title=response.title,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc
    conversation_store.append_message(
        conversation,
        MessageRole.USER,
        f"Plan {request.days} days in {request.destination}, budget={request.budget}, interests={request.interests}",
    )
    conversation_store.append_message(conversation, MessageRole.ASSISTANT, response.summary)
    saved_trip_plan = conversation_store.save_trip_plan(user_id, conversation, request, response)
    response.saved_trip_plan_id = saved_trip_plan.id
    response.conversation_id = conversation.id
    event_publisher.publish(
        "trip.plan.created",
        user_id,
        {
            "tripPlanId": saved_trip_plan.id,
            "conversationId": conversation.id,
            "destination": request.destination,
            "days": request.days,
        },
    )
    return response


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user_id: str = Depends(get_user_id)) -> ChatResponse:
    try:
        return handle_chat(user_id, request, conversation_store, settings)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc


@app.get("/api/v1/me/profile", response_model=UserProfile)
def get_profile(user_id: str = Depends(get_user_id)) -> UserProfile:
    return profile_store.get(user_id)


@app.patch("/api/v1/me/profile", response_model=UserProfile)
def update_profile(request: UserProfileUpdateRequest, user_id: str = Depends(get_user_id)) -> UserProfile:
    profile = profile_store.update(user_id, request)
    event_publisher.publish(
        "user.profile.updated",
        user_id,
        {"updatedFields": _updated_fields(request.model_fields_set)},
    )
    return profile


@app.get("/api/v1/conversations", response_model=ConversationListResponse)
def list_conversations(
    user_id: str = Depends(get_user_id),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    query: str = Query(default="", max_length=80),
) -> ConversationListResponse:
    return conversation_store.list(user_id=user_id, page=page, page_size=page_size, query=query)


@app.get("/api/v1/conversations/{conversation_id}", response_model=Conversation)
def get_conversation(conversation_id: str, user_id: str = Depends(get_user_id)) -> Conversation:
    try:
        return conversation_store.get(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc


@app.patch("/api/v1/conversations/{conversation_id}", response_model=Conversation)
def update_conversation(
    conversation_id: str,
    request: ConversationUpdateRequest,
    user_id: str = Depends(get_user_id),
) -> Conversation:
    try:
        conversation = conversation_store.update_title(user_id, conversation_id, request.title)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc
    event_publisher.publish(
        "agent.conversation.updated",
        user_id,
        {"conversationId": conversation_id, "updatedFields": ["title"]},
    )
    return conversation


@app.get("/api/v1/conversations/{conversation_id}/summary", response_model=ConversationSummary)
def get_conversation_summary(conversation_id: str, user_id: str = Depends(get_user_id)) -> ConversationSummary:
    try:
        conversation_store.get(user_id, conversation_id)
        return summary_store.get(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc
    except ConversationSummaryNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_SUMMARY_NOT_FOUND", "message": "Conversation summary not found"}) from exc


@app.post("/api/v1/conversations/{conversation_id}/summary", response_model=ConversationSummary)
def create_conversation_summary(conversation_id: str, user_id: str = Depends(get_user_id)) -> ConversationSummary:
    try:
        return conversation_summarizer.handle(
            SummarizeConversationCommand(
                user_id=user_id,
                conversation_id=conversation_id,
                requested_by="manual_api",
            )
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc


@app.post(
    "/api/v1/conversations/{conversation_id}/summary-jobs",
    response_model=ConversationSummaryJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_conversation_summary_job(conversation_id: str, user_id: str = Depends(get_user_id)) -> ConversationSummaryJob:
    try:
        conversation = conversation_store.get(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc

    if not event_publisher.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MESSAGE_QUEUE_DISABLED", "message": "Message queue is not configured"},
        )

    job = summary_job_store.create(user_id, conversation_id, CONVERSATION_SUMMARY_REQUESTED_EVENT)
    published = event_publisher.publish_required(
        CONVERSATION_SUMMARY_REQUESTED_EVENT,
        user_id,
        {
            "summaryJobId": job.id,
            "conversationId": conversation_id,
            "requestedBy": "async_api",
            "messageCount": len(conversation.messages),
        },
    )
    if not published:
        summary_job_store.mark_failed(user_id, job.id, "Summary job could not be queued")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MESSAGE_QUEUE_PUBLISH_FAILED", "message": "Summary job could not be queued"},
        )

    return job


@app.get("/api/v1/conversations/{conversation_id}/summary-jobs/latest", response_model=ConversationSummaryJob)
def get_latest_conversation_summary_job(
    conversation_id: str,
    user_id: str = Depends(get_user_id),
) -> ConversationSummaryJob:
    try:
        conversation_store.get(user_id, conversation_id)
        return summary_job_store.get_latest(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc
    except ConversationSummaryJobNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONVERSATION_SUMMARY_JOB_NOT_FOUND", "message": "Conversation summary job not found"},
        ) from exc


@app.delete("/api/v1/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, user_id: str = Depends(get_user_id)) -> Response:
    try:
        summary_job_store.delete_for_conversation(user_id, conversation_id)
        summary_store.delete_for_conversation(user_id, conversation_id)
        conversation_store.delete(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc
    event_publisher.publish("agent.conversation.deleted", user_id, {"conversationId": conversation_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/trip-plans", response_model=TripPlanListResponse)
def list_trip_plans(
    user_id: str = Depends(get_user_id),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    favorite_only: bool = Query(default=False, alias="favoriteOnly"),
    query: str = Query(default="", max_length=80),
) -> TripPlanListResponse:
    return conversation_store.list_trip_plans(
        user_id=user_id,
        page=page,
        page_size=page_size,
        favorite_only=favorite_only,
        query=query,
    )


@app.get("/api/v1/trip-plans/{trip_plan_id}", response_model=SavedTripPlan)
def get_trip_plan(trip_plan_id: str, user_id: str = Depends(get_user_id)) -> SavedTripPlan:
    try:
        return conversation_store.get_trip_plan(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc


@app.patch("/api/v1/trip-plans/{trip_plan_id}", response_model=SavedTripPlan)
def update_trip_plan(
    trip_plan_id: str,
    request: TripPlanUpdateRequest,
    user_id: str = Depends(get_user_id),
) -> SavedTripPlan:
    try:
        trip_plan = conversation_store.update_trip_plan_favorite(user_id, trip_plan_id, request.favorite)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc
    event_publisher.publish(
        "trip.plan.updated",
        user_id,
        {"tripPlanId": trip_plan_id, "updatedFields": ["favorite"], "favorite": trip_plan.favorite},
    )
    return trip_plan


@app.delete("/api/v1/trip-plans/{trip_plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip_plan(trip_plan_id: str, user_id: str = Depends(get_user_id)) -> Response:
    try:
        conversation_store.delete_trip_plan(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc
    event_publisher.publish("trip.plan.deleted", user_id, {"tripPlanId": trip_plan_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


def _updated_fields(fields: set[str]) -> list[str]:
    return sorted(to_camel(field) for field in fields)


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=settings.auth_token_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _delete_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=settings.auth_cookie_secure,
    )


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :].strip()
    return None


def _get_current_auth_user(request: Request) -> AuthUser:
    token = request.cookies.get(AUTH_COOKIE_NAME) or _bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        )

    try:
        user_id = verify_access_token(settings, token)
        return user_store.get_user(user_id)
    except (InvalidCredentialsError, UserNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        ) from exc


def _check_auth_rate_limit(request: Request, action: str, email: str) -> None:
    key = f"{action}:{client_identifier(request)}:{email.strip().lower()}"
    decision = auth_rate_limiter.check(key)
    if decision.allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": "RATE_LIMITED", "message": "Too many authentication attempts"},
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )


def _list_all_conversations(user_id: str) -> list[Conversation]:
    page = 1
    page_size = 100
    conversations: list[Conversation] = []
    while True:
        response = conversation_store.list(user_id=user_id, page=page, page_size=page_size)
        conversations.extend(response.data)
        if page >= response.total_pages or not response.data:
            return conversations
        page += 1


def _list_all_trip_plans(user_id: str) -> list[SavedTripPlan]:
    page = 1
    page_size = 100
    trip_plans: list[SavedTripPlan] = []
    while True:
        response = conversation_store.list_trip_plans(user_id=user_id, page=page, page_size=page_size)
        trip_plans.extend(response.data)
        if page >= response.total_pages or not response.data:
            return trip_plans
        page += 1
