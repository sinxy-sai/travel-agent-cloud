import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from travel_common.app import add_cors, allowed_origins_from_env
from travel_common.proxy import check_upstream, proxy_request

from app.db import create_session_factory
from app.events import CONVERSATION_SUMMARY_REQUESTED_EVENT, create_event_publisher
from app.schemas import (
    Conversation,
    ConversationListResponse,
    ConversationSummary,
    ConversationSummaryJob,
    ConversationUpdateRequest,
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
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
session_factory = create_session_factory(DATABASE_URL) if DATABASE_URL else None
conversation_store = ConversationStore(session_factory) if session_factory else None
summary_store = ConversationSummaryStore(session_factory) if session_factory else None
summary_job_store = ConversationSummaryJobStore(session_factory) if session_factory else None
event_publisher = create_event_publisher(MESSAGE_QUEUE_URL, RPC_TIMEOUT_SECONDS)

app = FastAPI(title=APP_NAME, version="0.1.0")
add_cors(app, allowed_origins=ALLOWED_ORIGINS)


@app.get("/health")
async def health() -> dict[str, Any]:
    upstream = await check_upstream(f"{AGENT_RUNTIME_URL}/health")
    return {
        "status": "ok" if upstream["ok"] and conversation_store is not None else "degraded",
        "service": APP_NAME,
        "mode": "agent-api-service-with-runtime-fallback",
        "databaseEnabled": conversation_store is not None,
        "messageQueueEnabled": event_publisher.enabled,
        "upstreams": {"agentRuntime": upstream},
    }


@app.api_route("/api/v1/chat", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_chat(request: Request) -> Response:
    return await _proxy(request, "/internal/v1/agent/chat")


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
        user_id = _user_id_or_none(request)
        if user_id and conversation_store:
            return conversation_store.list(user_id, page, page_size, query)
    return await _proxy(request, "/api/v1/conversations")


@app.get("/api/v1/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str, request: Request) -> Any:
    user_id = _user_id_or_none(request)
    if not user_id or not conversation_store:
        return await _proxy(request, f"/api/v1/conversations/{conversation_id}")
    try:
        return conversation_store.get(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc


@app.patch("/api/v1/conversations/{conversation_id}", response_model=Conversation)
async def update_conversation(conversation_id: str, payload: ConversationUpdateRequest, request: Request) -> Any:
    user_id = _user_id_or_none(request)
    if not user_id or not conversation_store:
        return await _proxy(request, f"/api/v1/conversations/{conversation_id}")
    try:
        return conversation_store.update_title(user_id, conversation_id, payload.title)
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc


@app.get("/api/v1/conversations/{conversation_id}/summary", response_model=ConversationSummary)
async def get_conversation_summary(conversation_id: str, request: Request) -> Any:
    user_id = _user_id_or_none(request)
    if not user_id or not summary_store:
        return await _proxy(request, f"/api/v1/conversations/{conversation_id}/summary")
    try:
        return summary_store.get(user_id, conversation_id)
    except ConversationSummaryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONVERSATION_SUMMARY_NOT_FOUND", "message": "Conversation summary not found"},
        ) from exc


@app.post("/api/v1/conversations/{conversation_id}/summary", response_model=ConversationSummary)
async def create_conversation_summary(conversation_id: str, request: Request) -> Any:
    user_id = _user_id_or_none(request)
    if not user_id or not conversation_store or not summary_store:
        return await _proxy(request, f"/api/v1/conversations/{conversation_id}/summary")
    try:
        conversation = conversation_store.get(user_id, conversation_id)
        summary = build_conversation_summary(conversation.messages)
        return summary_store.save(user_id, conversation_id, summary, len(conversation.messages))
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc


@app.post(
    "/api/v1/conversations/{conversation_id}/summary-jobs",
    response_model=ConversationSummaryJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_conversation_summary_job(conversation_id: str, request: Request) -> Any:
    user_id = _user_id_or_none(request)
    if not user_id or not conversation_store or not summary_job_store:
        return await _proxy(request, f"/api/v1/conversations/{conversation_id}/summary-jobs")
    if not event_publisher.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MESSAGE_QUEUE_DISABLED", "message": "Message queue is not configured"},
        )
    try:
        conversation = conversation_store.get(user_id, conversation_id)
        job = summary_job_store.create(user_id, conversation_id, CONVERSATION_SUMMARY_REQUESTED_EVENT)
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
        summary_job_store.mark_failed(user_id, job.id, "Summary job could not be queued")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MESSAGE_QUEUE_PUBLISH_FAILED", "message": "Summary job could not be queued"},
        )
    return job


@app.get("/api/v1/conversations/{conversation_id}/summary-jobs/latest", response_model=ConversationSummaryJob)
async def get_latest_conversation_summary_job(conversation_id: str, request: Request) -> Any:
    user_id = _user_id_or_none(request)
    if not user_id or not conversation_store or not summary_job_store:
        return await _proxy(request, f"/api/v1/conversations/{conversation_id}/summary-jobs/latest")
    try:
        conversation_store.get(user_id, conversation_id)
        return summary_job_store.get_latest(user_id, conversation_id)
    except ConversationNotFoundError as exc:
        raise _conversation_not_found() from exc
    except ConversationSummaryJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONVERSATION_SUMMARY_JOB_NOT_FOUND", "message": "Conversation summary job not found"},
        ) from exc


@app.delete("/api/v1/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, request: Request) -> Response:
    user_id = _user_id_or_none(request)
    if not user_id or not conversation_store:
        return await _proxy(request, f"/api/v1/conversations/{conversation_id}")
    try:
        if summary_job_store:
            summary_job_store.delete_for_conversation(user_id, conversation_id)
        if summary_store:
            summary_store.delete_for_conversation(user_id, conversation_id)
        conversation_store.delete(user_id, conversation_id)
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
    )


def _user_id_or_none(request: Request) -> str | None:
    return current_user_id(request)


def _conversation_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"},
    )
