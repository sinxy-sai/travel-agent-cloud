import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from travel_common.app import add_cors, allowed_origins_from_env
from travel_common.internal_auth import (
    InternalServiceAuthMiddleware,
    RequestContextMiddleware,
    internal_service_headers,
    internal_service_token,
)
from travel_common.proxy import check_upstream, proxy_request

from app.db import create_session_factory
from app.events import CONVERSATION_SUMMARY_REQUESTED_EVENT, create_event_publisher
from app.schemas import (
    ChatRequest,
    ChatResponse,
    Conversation,
    ConversationListResponse,
    ConversationSummary,
    ConversationSummaryJob,
    ConversationUpdateRequest,
    MessageRole,
)
from app.store import (
    ConversationNotFoundError,
    ConversationStore,
    ConversationSummaryJobNotFoundError,
    ConversationSummaryJobStore,
    ConversationSummaryNotFoundError,
    ConversationSummaryStore,
    build_conversation_summary,
)
from app.users import current_user_id


APP_NAME = "Travel Agent Facade"
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("AGENT_SERVICE_REQUEST_TIMEOUT_SECONDS", "180"))
MESSAGE_QUEUE_URL = os.getenv("MESSAGE_QUEUE_URL", "").strip()
RPC_TIMEOUT_SECONDS = float(os.getenv("RPC_TIMEOUT_SECONDS", "5"))
ALLOWED_ORIGINS = allowed_origins_from_env()
INTERNAL_SERVICE_TOKEN = internal_service_token()
INTERNAL_SERVICE_HEADERS = internal_service_headers(INTERNAL_SERVICE_TOKEN)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
session_factory = create_session_factory(DATABASE_URL) if DATABASE_URL else None
conversation_store = ConversationStore(session_factory) if session_factory else None
summary_store = ConversationSummaryStore(session_factory) if session_factory else None
summary_job_store = ConversationSummaryJobStore(session_factory) if session_factory else None
event_publisher = create_event_publisher(MESSAGE_QUEUE_URL, RPC_TIMEOUT_SECONDS)

app = FastAPI(title=APP_NAME, version="0.1.0")
app.add_middleware(
    InternalServiceAuthMiddleware,
    token=INTERNAL_SERVICE_TOKEN,
    protected_prefixes=("/api/",),
)
app.add_middleware(RequestContextMiddleware)
add_cors(app, allowed_origins=ALLOWED_ORIGINS)


@app.get("/health")
async def health() -> dict[str, Any]:
    upstream = await check_upstream(f"{AGENT_RUNTIME_URL}/health")
    return {
        "status": "ok" if upstream["ok"] and conversation_store is not None else "degraded",
        "service": APP_NAME,
        "mode": "agent-api-service",
        "databaseEnabled": conversation_store is not None,
        "messageQueueEnabled": event_publisher.enabled,
        "upstreams": {"agentRuntime": upstream},
    }


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    user_id = _user_id_or_none(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        )
    store = _require_conversation_store()
    try:
        conversation = store.get_or_create(
            user_id=user_id,
            conversation_id=payload.conversation_id,
            mode=payload.mode,
            title=_title_from_message(payload.message),
        )
        store.append_message(conversation, MessageRole.USER, payload.message)
        runtime_response = await _runtime_json(
            request,
            "/internal/v1/agent/chat",
            payload.model_copy(update={"conversation_id": conversation.id}).model_dump(mode="json", by_alias=True),
        )
        assistant_content = str(runtime_response.get("message", {}).get("content", "")).strip()
        if not assistant_content:
            assistant_content = "I could not generate a response for this request."
        assistant_message = store.append_message(conversation, MessageRole.ASSISTANT, assistant_content)
        return ChatResponse(
            conversation_id=conversation.id,
            message=assistant_message,
            suggestions=list(runtime_response.get("suggestions") or []),
        )
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc


@app.api_route("/api/v1/agent", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_agent_root(request: Request) -> Response:
    return await _proxy(request, "/api/v1/agent")


@app.api_route("/api/v1/agent/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_agent(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/agent/{path}")


@app.api_route("/api/v1/conversations", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def conversations_root(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    query: str = Query(default="", max_length=80),
) -> Any:
    if request.method == "GET":
        return _require_conversation_store().list(_required_user_id(request), page, page_size, query)
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail={"code": "METHOD_NOT_ALLOWED", "message": "Use a supported conversation endpoint"},
    )


@app.get("/api/v1/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str, request: Request) -> Any:
    user_id = _required_user_id(request)
    store = _require_conversation_store()
    try:
        return store.get(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc


@app.patch("/api/v1/conversations/{conversation_id}", response_model=Conversation)
async def update_conversation(conversation_id: str, payload: ConversationUpdateRequest, request: Request) -> Any:
    user_id = _required_user_id(request)
    store = _require_conversation_store()
    try:
        return store.update_title(user_id, conversation_id, payload.title)
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc


@app.get("/api/v1/conversations/{conversation_id}/summary", response_model=ConversationSummary)
async def get_conversation_summary(conversation_id: str, request: Request) -> Any:
    user_id = _required_user_id(request)
    store = _require_summary_store()
    try:
        return store.get(user_id, conversation_id)
    except ConversationSummaryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONVERSATION_SUMMARY_NOT_FOUND", "message": "Conversation summary not found"},
        ) from exc


@app.post("/api/v1/conversations/{conversation_id}/summary", response_model=ConversationSummary)
async def create_conversation_summary(conversation_id: str, request: Request) -> Any:
    user_id = _required_user_id(request)
    conversation_store_local = _require_conversation_store()
    summary_store_local = _require_summary_store()
    try:
        conversation = conversation_store_local.get(user_id, conversation_id)
        summary = build_conversation_summary(conversation.messages)
        return summary_store_local.save(user_id, conversation_id, summary, len(conversation.messages))
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc


@app.post(
    "/api/v1/conversations/{conversation_id}/summary-jobs",
    response_model=ConversationSummaryJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_conversation_summary_job(conversation_id: str, request: Request) -> Any:
    user_id = _required_user_id(request)
    conversation_store_local = _require_conversation_store()
    summary_job_store_local = _require_summary_job_store()
    if not event_publisher.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MESSAGE_QUEUE_DISABLED", "message": "Message queue is not configured"},
        )
    try:
        conversation = conversation_store_local.get(user_id, conversation_id)
        job = summary_job_store_local.create(user_id, conversation_id, CONVERSATION_SUMMARY_REQUESTED_EVENT)
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc
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
        summary_job_store_local.mark_failed(user_id, job.id, "Summary job could not be queued")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MESSAGE_QUEUE_PUBLISH_FAILED", "message": "Summary job could not be queued"},
        )
    return job


@app.get("/api/v1/conversations/{conversation_id}/summary-jobs/latest", response_model=ConversationSummaryJob)
async def get_latest_conversation_summary_job(conversation_id: str, request: Request) -> Any:
    user_id = _required_user_id(request)
    conversation_store_local = _require_conversation_store()
    summary_job_store_local = _require_summary_job_store()
    try:
        conversation_store_local.get(user_id, conversation_id)
        return summary_job_store_local.get_latest(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc
    except ConversationSummaryJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONVERSATION_SUMMARY_JOB_NOT_FOUND", "message": "Conversation summary job not found"},
        ) from exc


@app.delete("/api/v1/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, request: Request) -> Response:
    user_id = _required_user_id(request)
    conversation_store_local = _require_conversation_store()
    try:
        if summary_job_store:
            summary_job_store.delete_for_conversation(user_id, conversation_id)
        if summary_store:
            summary_store.delete_for_conversation(user_id, conversation_id)
        conversation_store_local.delete(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _proxy(request: Request, path: str) -> Response:
    return await proxy_request(
        request,
        upstream_base_url=AGENT_RUNTIME_URL,
        path=path,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        service_boundary="travel-agent",
        extra_headers=INTERNAL_SERVICE_HEADERS,
    )


async def _runtime_json(request: Request, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    import httpx

    headers = dict(INTERNAL_SERVICE_HEADERS)
    user_id = _user_id_or_none(request)
    if user_id:
        headers["X-User-Id"] = user_id
    request_id = request.headers.get("X-Request-ID") or request.headers.get("x-request-id")
    if request_id:
        headers["X-Request-ID"] = request_id
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{AGENT_RUNTIME_URL}{path}", json=payload, headers=headers)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=_error_detail(response))
    parsed = response.json()
    return parsed if isinstance(parsed, dict) else {}


def _user_id_or_none(request: Request) -> str | None:
    return current_user_id(request)


def _required_user_id(request: Request) -> str:
    user_id = _user_id_or_none(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        )
    return user_id


def _require_conversation_store() -> ConversationStore:
    if not conversation_store:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "CONVERSATION_STORE_UNAVAILABLE", "message": "Conversation store is not configured"},
        )
    return conversation_store


def _require_summary_store() -> ConversationSummaryStore:
    if not summary_store:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SUMMARY_STORE_UNAVAILABLE", "message": "Summary store is not configured"},
        )
    return summary_store


def _require_summary_job_store() -> ConversationSummaryJobStore:
    if not summary_job_store:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SUMMARY_JOB_STORE_UNAVAILABLE", "message": "Summary job store is not configured"},
        )
    return summary_job_store


def _conversation_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"},
    )


def _title_from_message(message: str) -> str:
    normalized = " ".join(message.strip().split())
    return normalized[:60] if normalized else "New conversation"


def _error_detail(response) -> Any:
    try:
        return response.json().get("detail", response.text)
    except ValueError:
        return response.text
