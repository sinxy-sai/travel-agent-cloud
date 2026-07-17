import asyncio
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode
from uuid import UUID, uuid4

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse
from pydantic import ValidationError

from app.agent import handle_chat
from app.auth import (
    AUTH_COOKIE_NAME,
    AuthIdentityConflictError,
    DatabaseUserStore,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    UserNotFoundError,
    UserStore,
    create_access_token,
    verify_access_token_claims,
)
from app.auth_sessions import (
    AuthSessionNotFoundError,
    AuthSessionRevokedError,
    AuthSessionStore,
    DatabaseAuthSessionStore,
)
from app.auth_identities import (
    AuthIdentityNotFoundError,
    AuthIdentityStore,
    DatabaseAuthIdentityStore,
)
from app.auth_tokens import (
    TOKEN_PURPOSE_EMAIL_VERIFICATION,
    TOKEN_PURPOSE_PASSWORD_RESET,
    AuthTokenStore,
    DatabaseAuthTokenStore,
    InvalidAuthTokenError,
)
from app.conversations import (
    ConversationNotFoundError,
    ConversationStore,
    DatabaseConversationStore,
    TripPlanNotFoundError,
    TripPlanVersionConflictError,
    TripPlanVersionNotFoundError,
)
from app.data_sources import summarize_trip_plan_data_sources
from app.data_importer import UserDataImporter
from app.db import maybe_create_session_factory
from app.events import CONVERSATION_SUMMARY_REQUESTED_EVENT, create_event_publisher
from app.exporter import saved_trip_plan_to_markdown
from app.mailer import Mailer
from app.observability import RequestLoggingMiddleware, configure_logging
from app.object_storage import MinioObjectStorage, ObjectStorageError, ObjectStorageNotFoundError
from app.oauth import (
    GITHUB_PROVIDER,
    OAUTH_STATE_COOKIE_NAME,
    OAUTH_STATE_TTL_SECONDS,
    GitHubOAuthClient,
    OAuthConfigurationError,
    OAuthProfile,
    OAuthProviderError,
    OAuthStateError,
    create_oauth_state,
    verify_oauth_state,
)
from app.profiles import DatabaseUserProfileStore, UserProfileStore
from app.progress import trip_plan_progress
from app.schemas import (
    AuthAccountDeleteRequest,
    AuthEmailActionResponse,
    AuthIdentityListResponse,
    AuthEmailRequest,
    AuthLoginRequest,
    AuthPasswordChangeRequest,
    AuthPasswordResetConfirmRequest,
    AuthRegisterRequest,
    AuthSession,
    AuthSessionInfo,
    AuthSessionListResponse,
    AuthSessionRevokeAllResponse,
    AuthTokenConfirmRequest,
    AuthUser,
    AuthUserUpdateRequest,
    AnonymousDataSummary,
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
    TripPlanJob,
    TripPlanReviseRequest,
    TripPlanRestoreRequest,
    TripDayRegenerateRequest,
    TripPlanRequest,
    TripPlanResponse,
    TripPlanUpdateRequest,
    TripPlanVersionListResponse,
    UserDataExport,
    UserDataImportRequest,
    UserDataImportResponse,
    UserExportFile,
    UserProfile,
    UserProfileUpdateRequest,
    UserSecurityEventListResponse,
    to_camel,
)
from app.security import InternalServiceAuthMiddleware, SecurityHeadersMiddleware, client_identifier, create_auth_rate_limiter
from app.security_events import DatabaseUserSecurityEventStore, UserSecurityEventStore
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
from app.trip_plan_jobs import TripPlanJobNotFoundError, TripPlanJobStore
from app.travel_agent_service import TravelAgentService
from app.travel_tools import create_travel_tool_provider
from app.users import DEFAULT_USER_ID, USER_ID_PATTERN, get_user_id
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
trip_plan_job_store = TripPlanJobStore()
user_store = DatabaseUserStore(session_factory) if session_factory else UserStore()
security_event_store = (
    DatabaseUserSecurityEventStore(session_factory) if session_factory else UserSecurityEventStore()
)
auth_token_store = DatabaseAuthTokenStore(session_factory) if session_factory else AuthTokenStore()
auth_identity_store = DatabaseAuthIdentityStore(session_factory) if session_factory else AuthIdentityStore()
auth_session_store = DatabaseAuthSessionStore(session_factory) if session_factory else AuthSessionStore()
mailer = Mailer(settings)
event_publisher = create_event_publisher(settings)
conversation_summarizer = ConversationSummarizerWorker(conversation_store, summary_store, event_publisher)
user_data_importer = UserDataImporter(session_factory, conversation_store, profile_store, summary_store)
github_oauth_client = GitHubOAuthClient(settings)
object_storage = MinioObjectStorage(settings)
travel_tool_provider = create_travel_tool_provider(settings)
travel_agent_service = TravelAgentService(settings, travel_tool_provider)
auth_rate_limiter = create_auth_rate_limiter(
    redis_url=settings.redis_url,
    max_attempts=settings.auth_rate_limit_max_attempts,
    window_seconds=settings.auth_rate_limit_window_seconds,
    key_prefix=settings.redis_key_prefix,
)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(InternalServiceAuthMiddleware, token=settings.internal_service_token)
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
def health() -> dict[str, str | bool | dict[str, bool | str | list[str]]]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "llmEnabled": travel_agent_service.llm_enabled,
        "databaseEnabled": session_factory is not None,
        "messageQueueEnabled": event_publisher.enabled,
        "redisRateLimitEnabled": auth_rate_limiter.distributed,
        "objectStorageEnabled": object_storage.enabled,
        "githubOAuthEnabled": github_oauth_client.enabled,
        "agentEngine": travel_agent_service.engine_name,
        "agentEngineCapabilities": travel_agent_service.engine_capabilities.to_dict(),
        "travelToolsProvider": travel_tool_provider.name,
    }


@app.get("/api/v1/agent/status")
def agent_status() -> dict[str, object]:
    last_run_trace = travel_agent_service.last_run_trace
    return {
        "engine": travel_agent_service.engine_name,
        "llmEnabled": travel_agent_service.llm_enabled,
        "capabilities": travel_agent_service.engine_capabilities.to_dict(),
        "lastRunTrace": last_run_trace.to_dict() if last_run_trace else None,
        "recentRunTraces": [trace.to_dict() for trace in travel_agent_service.recent_run_traces],
        "runSummary": travel_agent_service.run_summary.to_dict(),
        "qualitySummary": travel_agent_service.quality_summary.to_dict(),
        "toolCallSummary": travel_agent_service.tool_call_summary.to_dict(),
        "toolCatalog": _travel_tool_catalog(),
    }


@app.get("/api/v1/agent/tools")
def agent_tools() -> dict[str, object]:
    return _travel_tool_catalog()


@app.get("/api/v1/agent/diagnostics")
def agent_diagnostics() -> dict[str, object]:
    capabilities = travel_agent_service.engine_capabilities
    run_summary = travel_agent_service.run_summary
    quality_summary = travel_agent_service.quality_summary
    tool_catalog = _travel_tool_catalog()
    checks = _agent_diagnostic_checks(capabilities, run_summary.total_runs, quality_summary, tool_catalog)
    status_counts: dict[str, int] = {}
    for check in checks:
        status_value = str(check["status"])
        status_counts[status_value] = status_counts.get(status_value, 0) + 1

    overall_status = "OK"
    if status_counts.get("FAILED", 0) > 0:
        overall_status = "FAILED"
    elif status_counts.get("DEGRADED", 0) > 0 or status_counts.get("DISABLED", 0) > 0:
        overall_status = "DEGRADED"

    last_run_trace = travel_agent_service.last_run_trace
    return {
        "status": overall_status,
        "engine": travel_agent_service.engine_name,
        "dependencyMode": capabilities.dependency_mode,
        "llmEnabled": travel_agent_service.llm_enabled,
        "toolProvider": travel_tool_provider.name,
        "checks": checks,
        "statusCounts": status_counts,
        "capabilities": capabilities.to_dict(),
        "toolCatalog": tool_catalog,
        "runSummary": run_summary.to_dict(),
        "qualitySummary": quality_summary.to_dict(),
        "lastRunTrace": last_run_trace.to_dict() if last_run_trace else None,
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
    session_info = _create_auth_session(request, user)
    token = create_access_token(settings, user.id, session_info.id)
    _set_auth_cookie(response, token)
    _send_email_verification(user)
    _record_security_event(request, user.id, "auth.registered")
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
    session_info = _create_auth_session(request, user)
    token = create_access_token(settings, user.id, session_info.id)
    _set_auth_cookie(response, token)
    _record_security_event(request, user.id, "auth.logged_in")
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


@app.get("/api/v1/auth/identities", response_model=AuthIdentityListResponse)
def list_current_auth_identities(request: Request) -> AuthIdentityListResponse:
    user = _get_current_auth_user(request)
    return AuthIdentityListResponse(data=auth_identity_store.list_for_user(user.id))


@app.get("/api/v1/auth/sessions", response_model=AuthSessionListResponse)
def list_current_auth_sessions(request: Request) -> AuthSessionListResponse:
    user = _get_current_auth_user(request)
    current_session_id = _get_current_auth_session_id(request)
    return AuthSessionListResponse(data=auth_session_store.list_for_user(user.id, current_session_id))


@app.delete("/api/v1/auth/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_current_auth_session(request: Request, session_id: str, response: Response) -> Response:
    user = _get_current_auth_user(request)
    current_session_id = _get_current_auth_session_id(request)
    try:
        auth_session_store.revoke(user.id, session_id)
    except AuthSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "Auth session not found"},
        ) from exc
    _record_security_event(
        request,
        user.id,
        "auth.session_revoked",
        {"current": session_id == current_session_id},
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    if session_id == current_session_id:
        _delete_auth_cookie(response)
    return response


@app.post("/api/v1/auth/sessions/revoke-all", response_model=AuthSessionRevokeAllResponse)
def revoke_other_auth_sessions(request: Request) -> AuthSessionRevokeAllResponse:
    user = _get_current_auth_user(request)
    current_session_id = _get_current_auth_session_id(request)
    revoked = auth_session_store.revoke_all(user.id, except_session_id=current_session_id)
    _record_security_event(request, user.id, "auth.sessions_revoked_all", {"revoked": revoked})
    return AuthSessionRevokeAllResponse(revoked=revoked)


@app.delete("/api/v1/auth/identities/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_current_auth_identity(request: Request, provider: str) -> Response:
    user = _get_current_auth_user(request)
    if provider != GITHUB_PROVIDER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "IDENTITY_NOT_FOUND", "message": "Auth identity not found"},
        )
    identities = auth_identity_store.list_for_user(user.id)
    provider_identity = next((identity for identity in identities if identity.provider == provider), None)
    if provider_identity and not user.password_configured and len(identities) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PASSWORD_REQUIRED",
                "message": "Set a project password before unlinking the only sign-in identity",
            },
        )
    try:
        auth_identity_store.delete_for_user(user.id, provider)
    except AuthIdentityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "IDENTITY_NOT_FOUND", "message": "Auth identity not found"},
        ) from exc
    _record_security_event(request, user.id, "auth.identity_unlinked", {"provider": provider})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/auth/oauth/github/start")
def start_github_oauth() -> RedirectResponse:
    try:
        state = create_oauth_state(settings, GITHUB_PROVIDER)
        redirect = RedirectResponse(github_oauth_client.authorization_url(state), status_code=status.HTTP_302_FOUND)
    except OAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OAUTH_PROVIDER_DISABLED", "message": "GitHub OAuth is not configured"},
        ) from exc
    _set_oauth_state_cookie(redirect, state)
    return redirect


@app.get("/api/v1/auth/oauth/github/callback")
def github_oauth_callback(
    request: Request,
    code: str = Query(default="", max_length=300),
    state: str = Query(default="", max_length=1000),
    error: str = Query(default="", max_length=120),
) -> RedirectResponse:
    if error:
        return _oauth_frontend_redirect("error", error)
    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME, "")
    if not state or not cookie_state or not hmac.compare_digest(state, cookie_state):
        return _oauth_frontend_redirect("error", "invalid_state")
    try:
        verify_oauth_state(settings, state, GITHUB_PROVIDER)
    except OAuthStateError:
        return _oauth_frontend_redirect("error", "invalid_state")
    if not code:
        return _oauth_frontend_redirect("error", "missing_code")

    try:
        profile = github_oauth_client.exchange_code(code)
        user, event_type = _resolve_oauth_user(request, profile)
    except (OAuthConfigurationError, OAuthProviderError, AuthIdentityConflictError, UserNotFoundError, ValueError):
        return _oauth_frontend_redirect("error", "github_login_failed")

    session_info = _create_auth_session(request, user)
    token = create_access_token(settings, user.id, session_info.id)
    redirect = _oauth_frontend_redirect("success")
    _set_auth_cookie(redirect, token)
    _delete_oauth_state_cookie(redirect)
    _record_security_event(request, user.id, event_type, {"provider": GITHUB_PROVIDER})
    return redirect


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
    _record_security_event(request, user.id, "auth.password_changed")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/auth/email-verification/request", response_model=AuthEmailActionResponse)
def request_email_verification(request: Request) -> AuthEmailActionResponse:
    user = _get_current_auth_user(request)
    _check_auth_rate_limit(request, "email-verification", user.id)
    if user.email_verified:
        return AuthEmailActionResponse(sent=False, delivery="already_verified")
    result = _send_email_verification(user)
    _record_security_event(request, user.id, "auth.email_verification_requested", {"delivery": result.delivery})
    return result


@app.post("/api/v1/auth/email-verification/confirm", response_model=AuthUser)
def confirm_email_verification(request: Request, payload: AuthTokenConfirmRequest) -> AuthUser:
    try:
        user_id = auth_token_store.consume(payload.token, TOKEN_PURPOSE_EMAIL_VERIFICATION)
        user = user_store.mark_email_verified(user_id)
    except (InvalidAuthTokenError, UserNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TOKEN", "message": "Verification link is invalid or expired"},
        ) from exc
    _record_security_event(request, user.id, "auth.email_verified")
    return user


@app.post("/api/v1/auth/password-reset/request", response_model=AuthEmailActionResponse)
def request_password_reset(request: Request, payload: AuthEmailRequest) -> AuthEmailActionResponse:
    _check_auth_rate_limit(request, "password-reset", payload.email)
    try:
        user = user_store.get_user_by_email(payload.email)
    except (UserNotFoundError, ValueError):
        return AuthEmailActionResponse(sent=True, delivery="accepted")

    generated = auth_token_store.create(
        user.id,
        TOKEN_PURPOSE_PASSWORD_RESET,
        settings.password_reset_token_ttl_seconds,
    )
    delivery = mailer.send_password_reset(user.email, generated.token)
    if settings.email_provider.strip().lower() in {"", "mock"}:
        response = AuthEmailActionResponse(sent=delivery.sent, delivery=delivery.delivery, expires_at=generated.expires_at)
        response.dev_token = generated.token
        response.action_url = mailer.password_reset_url(generated.token)
    else:
        response = AuthEmailActionResponse(sent=True, delivery="accepted")
    _record_security_event(request, user.id, "auth.password_reset_requested", {"delivery": delivery.delivery})
    return response


@app.post("/api/v1/auth/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(request: Request, payload: AuthPasswordResetConfirmRequest) -> Response:
    current_user = _get_optional_current_auth_user(request)
    current_session_id = _get_current_auth_session_id(request) if current_user else None
    try:
        user_id = auth_token_store.consume(payload.token, TOKEN_PURPOSE_PASSWORD_RESET)
        user_store.reset_password(user_id, payload.new_password)
        revoke_except_session_id = current_session_id if current_user and current_user.id == user_id else None
        revoked = auth_session_store.revoke_all(user_id, except_session_id=revoke_except_session_id)
        _record_security_event(request, user_id, "auth.password_reset_completed")
        if revoked:
            _record_security_event(request, user_id, "auth.sessions_revoked_all", {"revoked": revoked})
    except (InvalidAuthTokenError, UserNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TOKEN", "message": "Password reset link is invalid or expired"},
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/v1/auth/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_auth_user(request: Request, payload: AuthAccountDeleteRequest, response: Response) -> Response:
    user = _get_current_auth_user(request)
    _check_auth_rate_limit(request, "delete-account", user.id)
    try:
        user_store.authenticate(user.email, payload.current_password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Current password is incorrect"},
        ) from exc
    if object_storage.enabled:
        try:
            object_storage.delete_user_exports(user.id)
        except ObjectStorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "OBJECT_STORAGE_UNAVAILABLE", "message": "Could not delete stored export files"},
            ) from exc
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

    security_event_store.delete_for_user(user.id)
    auth_session_store.revoke_all(user.id)
    response.status_code = status.HTTP_204_NO_CONTENT
    _delete_auth_cookie(response)
    return response


@app.get("/api/v1/me/export", response_model=UserDataExport)
def export_current_user_data(request: Request) -> UserDataExport:
    user = _get_current_auth_user(request)
    _require_verified_email(user)
    exported = _export_user_data(user.id, user)
    _record_security_event(
        request,
        user.id,
        "user.data_exported",
        {
            "conversations": len(exported.conversations),
            "conversationSummaries": len(exported.conversation_summaries),
            "tripPlans": len(exported.trip_plans),
        },
    )
    return exported


@app.post("/api/v1/me/export-files", response_model=UserExportFile, status_code=status.HTTP_201_CREATED)
def create_current_user_export_file(request: Request) -> UserExportFile:
    user = _get_current_auth_user(request)
    _require_verified_email(user)
    if not object_storage.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OBJECT_STORAGE_DISABLED", "message": "Object storage is not configured"},
        )

    exported = _export_user_data(user.id, user)
    payload = json.dumps(
        exported.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    export_id = str(uuid4())
    try:
        object_storage.put_user_export(user.id, export_id, payload)
    except ObjectStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OBJECT_STORAGE_UNAVAILABLE", "message": "Could not store export file"},
        ) from exc

    filename = f"travel-agent-data-{exported.exported_at.date().isoformat()}.json"
    _record_security_event(request, user.id, "user.export_file_created", {"sizeBytes": len(payload)})
    return UserExportFile(
        id=export_id,
        filename=filename,
        content_type="application/json",
        size_bytes=len(payload),
        created_at=exported.exported_at,
        download_url=f"/api/v1/me/export-files/{export_id}",
    )


@app.get("/api/v1/me/export-files/{export_id}")
def download_current_user_export_file(request: Request, export_id: UUID) -> Response:
    user = _get_current_auth_user(request)
    _require_verified_email(user)
    if not object_storage.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OBJECT_STORAGE_DISABLED", "message": "Object storage is not configured"},
        )
    try:
        payload = object_storage.get_user_export(user.id, str(export_id))
    except ObjectStorageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EXPORT_FILE_NOT_FOUND", "message": "Export file not found"},
        ) from exc
    except ObjectStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OBJECT_STORAGE_UNAVAILABLE", "message": "Could not read export file"},
        ) from exc

    filename = f"travel-agent-data-{datetime.now(UTC).date().isoformat()}.json"
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/v1/me/import", response_model=UserDataImportResponse)
def import_current_user_data(request: Request, payload: UserDataImportRequest) -> UserDataImportResponse:
    user = _get_current_auth_user(request)
    _require_verified_email(user)
    _check_auth_rate_limit(request, "import-data", user.id)
    result = user_data_importer.import_user_data(user.id, payload)
    _record_security_event(
        request,
        user.id,
        "user.data_imported",
        {
            "conversationsImported": result.conversations_imported,
            "conversationSummariesImported": result.conversation_summaries_imported,
            "tripPlansImported": result.trip_plans_imported,
            "skippedItems": result.skipped_items,
        },
    )
    event_publisher.publish(
        "user.data.imported",
        user.id,
        {
            "conversationsImported": result.conversations_imported,
            "conversationSummariesImported": result.conversation_summaries_imported,
            "tripPlansImported": result.trip_plans_imported,
            "skippedItems": result.skipped_items,
        },
    )
    return result


@app.get("/api/v1/me/anonymous-data/summary", response_model=AnonymousDataSummary)
def summarize_current_anonymous_data(request: Request) -> AnonymousDataSummary:
    user = _get_current_auth_user(request)
    anonymous_user_id = _anonymous_user_id_from_header(request)
    if anonymous_user_id == user.id:
        return AnonymousDataSummary(has_data=False, conversations=0, conversation_summaries=0, trip_plans=0)
    return _anonymous_data_summary(anonymous_user_id)


@app.post("/api/v1/me/anonymous-data/import", response_model=UserDataImportResponse)
def import_current_anonymous_data(request: Request) -> UserDataImportResponse:
    user = _get_current_auth_user(request)
    _require_verified_email(user)
    anonymous_user_id = _anonymous_user_id_from_header(request)
    if anonymous_user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_ANONYMOUS_USER", "message": "Anonymous user id must be different from account id"},
        )

    payload = _clone_user_data_for_import(anonymous_user_id, user)
    result = user_data_importer.import_user_data(user.id, payload)
    _record_security_event(
        request,
        user.id,
        "user.anonymous_data_imported",
        {
            "sourceUserId": _redact_user_id(anonymous_user_id),
            "conversationsImported": result.conversations_imported,
            "conversationSummariesImported": result.conversation_summaries_imported,
            "tripPlansImported": result.trip_plans_imported,
            "skippedItems": result.skipped_items,
        },
    )
    event_publisher.publish(
        "user.anonymous_data.imported",
        user.id,
        {
            "conversationsImported": result.conversations_imported,
            "conversationSummariesImported": result.conversation_summaries_imported,
            "tripPlansImported": result.trip_plans_imported,
            "skippedItems": result.skipped_items,
        },
    )
    return result


@app.get("/api/v1/auth/security-events", response_model=UserSecurityEventListResponse)
def list_current_user_security_events(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50, alias="pageSize"),
) -> UserSecurityEventListResponse:
    user = _get_current_auth_user(request)
    return security_event_store.list(user.id, page, page_size)


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response) -> Response:
    try:
        user = _get_current_auth_user(request)
        session_id = _get_current_auth_session_id(request)
        if session_id:
            auth_session_store.revoke(user.id, session_id)
            _record_security_event(request, user.id, "auth.session_revoked", {"current": True})
        _record_security_event(request, user.id, "auth.logged_out")
    except HTTPException:
        pass
    response.status_code = status.HTTP_204_NO_CONTENT
    _delete_auth_cookie(response)
    return response


@app.post("/internal/v1/trip-plan", response_model=TripPlanResponse)
@app.post("/api/v1/trip-plan", response_model=TripPlanResponse)
def create_trip_plan(request: TripPlanRequest, user_id: str = Depends(get_user_id)) -> TripPlanResponse:
    return _create_trip_plan_for_user(request, user_id)


@app.post("/internal/v1/trip-plan-jobs", response_model=TripPlanJob, status_code=status.HTTP_202_ACCEPTED)
@app.post("/api/v1/trip-plan-jobs", response_model=TripPlanJob, status_code=status.HTTP_202_ACCEPTED)
def create_trip_plan_job(
    request: TripPlanRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
) -> TripPlanJob:
    job = trip_plan_job_store.create(user_id)
    background_tasks.add_task(_run_trip_plan_job, user_id, job.id, request.model_copy(deep=True))
    return job


@app.get("/internal/v1/trip-plan-jobs/{job_id}", response_model=TripPlanJob)
@app.get("/api/v1/trip-plan-jobs/{job_id}", response_model=TripPlanJob)
def get_trip_plan_job(job_id: str, user_id: str = Depends(get_user_id)) -> TripPlanJob:
    try:
        return trip_plan_job_store.get(user_id, job_id)
    except TripPlanJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_JOB_NOT_FOUND", "message": "Trip plan job not found"}) from exc


@app.get("/internal/v1/trip-plan-jobs/{job_id}/events")
@app.get("/api/v1/trip-plan-jobs/{job_id}/events")
def stream_trip_plan_job(job_id: str, user_id: str = Depends(get_user_id)) -> StreamingResponse:
    try:
        trip_plan_job_store.get(user_id, job_id)
    except TripPlanJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_JOB_NOT_FOUND", "message": "Trip plan job not found"}) from exc
    return StreamingResponse(
        _trip_plan_job_event_stream(user_id, job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _trip_plan_job_event_stream(user_id: str, job_id: str):
    while True:
        try:
            job = trip_plan_job_store.get(user_id, job_id)
        except TripPlanJobNotFoundError:
            yield 'event: error\ndata: {"message":"Trip plan job not found"}\n\n'
            return
        yield f"data: {job.model_dump_json(by_alias=True)}\n\n"
        if job.status in {"SUCCEEDED", "FAILED"}:
            return
        await asyncio.sleep(0.8)


def _run_trip_plan_job(user_id: str, job_id: str, request: TripPlanRequest) -> None:
    try:
        trip_plan_job_store.mark_running(user_id, job_id)
        response = _create_trip_plan_for_user(
            request,
            user_id,
            on_stage=lambda stage_key: trip_plan_job_store.mark_stage_running(user_id, job_id, stage_key),
        )
        trip_plan_job_store.mark_succeeded(user_id, job_id, response)
    except Exception as exc:
        trip_plan_job_store.mark_failed(user_id, job_id, str(exc) or exc.__class__.__name__)


def _create_trip_plan_for_user(
    request: TripPlanRequest,
    user_id: str,
    on_stage=None,
) -> TripPlanResponse:
    with trip_plan_progress(on_stage):
        response = travel_agent_service.generate_trip_plan(request)
    if travel_agent_service.last_run_trace and travel_agent_service.last_run_trace.operation == "trip_plan":
        response.data_sources = summarize_trip_plan_data_sources(travel_agent_service.last_run_trace)
    if on_stage:
        on_stage("saving")
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
    saved_trip_plan = _save_generated_trip_plan(user_id, conversation.id, request, response)
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


def _save_generated_trip_plan(
    user_id: str,
    conversation_id: str,
    request: TripPlanRequest,
    response: TripPlanResponse,
) -> SavedTripPlan:
    if settings.travel_trip_url.strip():
        try:
            with httpx.Client(timeout=settings.travel_trip_timeout_seconds) as client:
                trip_response = client.post(
                    f"{settings.travel_trip_url.rstrip('/')}/internal/v1/trip-plans",
                    headers=_internal_service_headers(user_id=user_id),
                    json={
                        "request": request.model_dump(mode="json", by_alias=True),
                        "plan": response.model_dump(mode="json", by_alias=True),
                        "conversationId": conversation_id,
                    },
                )
                trip_response.raise_for_status()
            return SavedTripPlan.model_validate(trip_response.json())
        except (httpx.HTTPError, ValueError):
            pass

    conversation = conversation_store.get(user_id, conversation_id)
    return conversation_store.save_trip_plan(user_id, conversation, request, response)


def _update_trip_plan_content(
    user_id: str,
    trip_plan_id: str,
    request: TripPlanUpdateRequest,
    *,
    source: str,
) -> SavedTripPlan:
    if settings.travel_trip_url.strip():
        try:
            with httpx.Client(timeout=settings.travel_trip_timeout_seconds) as client:
                trip_response = client.patch(
                    f"{settings.travel_trip_url.rstrip('/')}/internal/v1/trip-plans/{trip_plan_id}",
                    headers=_internal_service_headers(user_id=user_id),
                    json={
                        **request.model_dump(mode="json", by_alias=True, exclude_none=True),
                        "source": source,
                    },
                )
            if trip_response.status_code == status.HTTP_404_NOT_FOUND:
                raise TripPlanNotFoundError(trip_plan_id)
            if trip_response.status_code == status.HTTP_409_CONFLICT:
                raise TripPlanVersionConflictError(trip_plan_id)
            trip_response.raise_for_status()
            return SavedTripPlan.model_validate(trip_response.json())
        except (TripPlanNotFoundError, TripPlanVersionConflictError):
            raise
        except (httpx.HTTPError, ValueError):
            pass

    return conversation_store.update_trip_plan(user_id, trip_plan_id, request, source=source)


def _internal_service_headers(*, user_id: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {"X-Request-ID": str(uuid4())}
    if user_id:
        headers["X-User-Id"] = user_id
    if settings.internal_service_token.strip():
        headers["X-Travel-Internal-Token"] = settings.internal_service_token.strip()
    return headers


@app.post("/internal/v1/agent/chat", response_model=ChatResponse)
@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user_id: str = Depends(get_user_id)) -> ChatResponse:
    try:
        return handle_chat(user_id, request, conversation_store, travel_agent_service)
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


@app.get("/api/v1/trip-plans/{trip_plan_id}/versions", response_model=TripPlanVersionListResponse)
def list_trip_plan_versions(
    trip_plan_id: str,
    user_id: str = Depends(get_user_id),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
) -> TripPlanVersionListResponse:
    try:
        return conversation_store.list_trip_plan_versions(user_id, trip_plan_id, page, page_size)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc


@app.patch("/api/v1/trip-plans/{trip_plan_id}", response_model=SavedTripPlan)
def update_trip_plan(
    trip_plan_id: str,
    request: TripPlanUpdateRequest,
    user_id: str = Depends(get_user_id),
) -> SavedTripPlan:
    try:
        trip_plan = conversation_store.update_trip_plan(user_id, trip_plan_id, request)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc
    except TripPlanVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before saving",
            },
        ) from exc
    updated_fields = []
    if request.favorite is not None:
        updated_fields.append("favorite")
    if request.plan is not None:
        updated_fields.append("plan")
    event_publisher.publish(
        "trip.plan.updated",
        user_id,
        {
            "tripPlanId": trip_plan_id,
            "updatedFields": updated_fields,
            "favorite": trip_plan.favorite,
            "version": trip_plan.version,
        },
    )
    return trip_plan


@app.post("/api/v1/trip-plans/{trip_plan_id}/versions/{version_id}/restore", response_model=SavedTripPlan)
def restore_trip_plan_version(
    trip_plan_id: str,
    version_id: str,
    request: TripPlanRestoreRequest,
    user_id: str = Depends(get_user_id),
) -> SavedTripPlan:
    try:
        trip_plan = conversation_store.restore_trip_plan_version(
            user_id,
            trip_plan_id,
            version_id,
            request.expected_version,
        )
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc
    except TripPlanVersionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "TRIP_PLAN_VERSION_NOT_FOUND", "message": "Trip plan version not found"},
        ) from exc
    except TripPlanVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before restoring",
            },
        ) from exc

    if trip_plan.conversation_id:
        try:
            conversation = conversation_store.get(user_id, trip_plan.conversation_id)
            conversation_store.append_message(conversation, MessageRole.USER, "Restore itinerary version")
            conversation_store.append_message(
                conversation,
                MessageRole.ASSISTANT,
                f"Restored itinerary version as v{trip_plan.version}: {trip_plan.title}",
            )
        except ConversationNotFoundError:
            pass

    event_publisher.publish(
        "trip.plan.version.restored",
        user_id,
        {
            "tripPlanId": trip_plan_id,
            "versionId": version_id,
            "version": trip_plan.version,
        },
    )
    return trip_plan


@app.post("/internal/v1/trip-plans/{trip_plan_id}/revise", response_model=SavedTripPlan)
@app.post("/api/v1/trip-plans/{trip_plan_id}/revise", response_model=SavedTripPlan)
def revise_trip_plan(
    trip_plan_id: str,
    request: TripPlanReviseRequest,
    user_id: str = Depends(get_user_id),
) -> SavedTripPlan:
    try:
        saved_trip_plan = conversation_store.get_trip_plan(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc
    if request.expected_version != saved_trip_plan.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before saving",
            },
        )

    revised_plan = travel_agent_service.revise_trip_plan(saved_trip_plan, request.instruction)
    revised_plan = revised_plan.model_copy(
        update={
            "saved_trip_plan_id": saved_trip_plan.id,
            "conversation_id": saved_trip_plan.conversation_id,
        }
    )

    try:
        trip_plan = _update_trip_plan_content(
            user_id,
            trip_plan_id,
            TripPlanUpdateRequest(plan=revised_plan, expected_version=request.expected_version),
            source="agent_revision",
        )
    except TripPlanVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before saving",
            },
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "TRIP_PLAN_REVISION_INVALID", "message": "Revised trip plan was invalid"},
        ) from exc

    if trip_plan.conversation_id:
        try:
            conversation = conversation_store.get(user_id, trip_plan.conversation_id)
            conversation_store.append_message(conversation, MessageRole.USER, f"Revise itinerary: {request.instruction}")
            conversation_store.append_message(
                conversation,
                MessageRole.ASSISTANT,
                f"Revised itinerary: {trip_plan.plan.summary}",
            )
        except ConversationNotFoundError:
            pass

    event_publisher.publish(
        "trip.plan.revised",
        user_id,
        {
            "tripPlanId": trip_plan_id,
            "version": trip_plan.version,
        },
    )
    return trip_plan


@app.post("/internal/v1/trip-plans/{trip_plan_id}/days/{day}/regenerate", response_model=SavedTripPlan)
@app.post("/api/v1/trip-plans/{trip_plan_id}/days/{day}/regenerate", response_model=SavedTripPlan)
def regenerate_trip_plan_day(
    trip_plan_id: str,
    request: TripDayRegenerateRequest,
    day: int = Path(ge=1, le=30),
    user_id: str = Depends(get_user_id),
) -> SavedTripPlan:
    try:
        saved_trip_plan = conversation_store.get_trip_plan(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc
    if request.expected_version != saved_trip_plan.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before saving",
            },
        )

    if not any(item.day == day for item in saved_trip_plan.plan.days):
        raise HTTPException(
            status_code=404,
            detail={"code": "TRIP_PLAN_DAY_NOT_FOUND", "message": "Trip plan day not found"},
        )

    regenerated_day = travel_agent_service.regenerate_trip_day(saved_trip_plan, day, request.instruction)
    updated_plan = saved_trip_plan.plan.model_copy(
        update={
            "days": [regenerated_day if item.day == day else item for item in saved_trip_plan.plan.days],
            "saved_trip_plan_id": saved_trip_plan.id,
            "conversation_id": saved_trip_plan.conversation_id,
        }
    )

    try:
        trip_plan = _update_trip_plan_content(
            user_id,
            trip_plan_id,
            TripPlanUpdateRequest(plan=updated_plan, expected_version=request.expected_version),
            source="day_regeneration",
        )
    except TripPlanVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before saving",
            },
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "TRIP_DAY_REGENERATION_INVALID", "message": "Regenerated trip day was invalid"},
        ) from exc

    if trip_plan.conversation_id:
        try:
            conversation = conversation_store.get(user_id, trip_plan.conversation_id)
            conversation_store.append_message(conversation, MessageRole.USER, f"Regenerate day {day}: {request.instruction}")
            conversation_store.append_message(
                conversation,
                MessageRole.ASSISTANT,
                f"Updated day {day}: {regenerated_day.theme}",
            )
        except ConversationNotFoundError:
            pass

    event_publisher.publish(
        "trip.plan.day.regenerated",
        user_id,
        {
            "tripPlanId": trip_plan_id,
            "day": day,
            "version": trip_plan.version,
        },
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

    return PlainTextResponse(
        content=saved_trip_plan_to_markdown(saved_trip_plan),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": _content_disposition_for_download(saved_trip_plan.title)},
    )


def _download_filename(title: str) -> str:
    safe_title = "".join(character if character.isascii() and character.isalnum() else "-" for character in title.lower())
    safe_title = "-".join(part for part in safe_title.split("-") if part)
    return f"{safe_title or 'trip-plan'}.md"


def _content_disposition_for_download(title: str) -> str:
    ascii_filename = _download_filename(title)
    utf8_filename = quote(f"{title.strip() or 'trip-plan'}.md")
    return f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{utf8_filename}"


def _updated_fields(fields: set[str]) -> list[str]:
    return sorted(to_camel(field) for field in fields)


def _resolve_oauth_user(request: Request, profile: OAuthProfile) -> tuple[AuthUser, str]:
    current_user = _get_optional_current_auth_user(request)
    try:
        identity = auth_identity_store.get_by_provider_user_id(profile.provider, profile.provider_user_id)
        if current_user and identity.user_id != current_user.id:
            raise AuthIdentityConflictError(profile.provider)
        user = user_store.get_user(identity.user_id)
        auth_identity_store.upsert(
            user.id,
            profile.provider,
            profile.provider_user_id,
            email=profile.email,
            display_name=profile.display_name,
            avatar_url=profile.avatar_url,
        )
        return user, "auth.oauth_logged_in"
    except AuthIdentityNotFoundError:
        pass

    if current_user:
        auth_identity_store.upsert(
            current_user.id,
            profile.provider,
            profile.provider_user_id,
            email=profile.email,
            display_name=profile.display_name,
            avatar_url=profile.avatar_url,
        )
        return current_user, "auth.identity_linked"

    try:
        user = user_store.get_user_by_email(profile.email)
        if not user.email_verified:
            user = user_store.mark_email_verified(user.id)
    except UserNotFoundError:
        try:
            user = user_store.create_oauth_user(profile.email, profile.display_name)
        except EmailAlreadyRegisteredError:
            user = user_store.get_user_by_email(profile.email)
            if not user.email_verified:
                user = user_store.mark_email_verified(user.id)

    auth_identity_store.upsert(
        user.id,
        profile.provider,
        profile.provider_user_id,
        email=profile.email,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
    )
    return user, "auth.oauth_logged_in"


def _oauth_frontend_redirect(status_value: str, error: str = "") -> RedirectResponse:
    params = {"authAction": "oauth-github", "authStatus": status_value}
    if error:
        params["authError"] = error
    return RedirectResponse(
        f"{settings.public_app_url.rstrip('/')}?{urlencode(params)}",
        status_code=status.HTTP_302_FOUND,
    )


def _set_oauth_state_cookie(response: Response, state_value: str) -> None:
    response.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        state_value,
        max_age=OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _delete_oauth_state_cookie(response: Response) -> None:
    response.delete_cookie(
        OAUTH_STATE_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=settings.auth_cookie_secure,
    )


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


def _get_current_auth_claims(request: Request):
    token = request.cookies.get(AUTH_COOKIE_NAME) or _bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        )

    try:
        claims = verify_access_token_claims(settings, token)
        if claims.session_id:
            auth_session_store.require_active(claims.user_id, claims.session_id)
        return claims
    except (InvalidCredentialsError, AuthSessionNotFoundError, AuthSessionRevokedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        ) from exc


def _get_current_auth_user(request: Request) -> AuthUser:
    claims = _get_current_auth_claims(request)
    try:
        return user_store.get_user(claims.user_id)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        ) from exc


def _get_current_auth_session_id(request: Request) -> str | None:
    return _get_current_auth_claims(request).session_id


def _get_optional_current_auth_user(request: Request) -> AuthUser | None:
    try:
        return _get_current_auth_user(request)
    except HTTPException:
        return None


def _require_verified_email(user: AuthUser) -> None:
    if user.email_verified:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "EMAIL_NOT_VERIFIED", "message": "Verify your email before managing account data"},
    )


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


def _create_auth_session(request: Request, user: AuthUser) -> AuthSessionInfo:
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.auth_token_ttl_seconds)
    session_info = auth_session_store.create(
        user.id,
        expires_at,
        client_identifier=client_identifier(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    _record_security_event(
        request,
        user.id,
        "auth.session_created",
        {"sessionId": _redact_user_id(session_info.id)},
    )
    return session_info


def _send_email_verification(user: AuthUser) -> AuthEmailActionResponse:
    generated = auth_token_store.create(
        user.id,
        TOKEN_PURPOSE_EMAIL_VERIFICATION,
        settings.email_verification_token_ttl_seconds,
    )
    delivery = mailer.send_email_verification(user.email, generated.token)
    response = AuthEmailActionResponse(sent=delivery.sent, delivery=delivery.delivery, expires_at=generated.expires_at)
    if settings.email_provider.strip().lower() in {"", "mock"}:
        response.dev_token = generated.token
        response.action_url = mailer.verification_url(generated.token)
    return response


def _record_security_event(
    request: Request,
    user_id: str,
    event_type: str,
    details: dict | None = None,
) -> None:
    security_event_store.record(
        user_id,
        event_type,
        client_identifier=client_identifier(request),
        details=details,
    )


def _anonymous_user_id_from_header(request: Request) -> str:
    x_user_id = request.headers.get("X-User-Id", "").strip()
    if not x_user_id or x_user_id == DEFAULT_USER_ID or not USER_ID_PATTERN.fullmatch(x_user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_ANONYMOUS_USER", "message": "Valid X-User-Id header is required"},
        )
    return x_user_id


def _export_user_data(user_id: str, user: AuthUser) -> UserDataExport:
    conversations = _list_all_conversations(user_id)
    summaries = []
    for conversation in conversations:
        try:
            summaries.append(summary_store.get(user_id, conversation.id))
        except ConversationSummaryNotFoundError:
            continue

    return UserDataExport(
        exported_at=datetime.now(UTC),
        user=user,
        profile=profile_store.get(user_id),
        conversations=conversations,
        conversation_summaries=summaries,
        trip_plans=_list_all_trip_plans(user_id),
    )


def _anonymous_data_summary(user_id: str) -> AnonymousDataSummary:
    conversations = _list_all_conversations(user_id)
    trip_plans = _list_all_trip_plans(user_id)
    summary_count = 0
    for conversation in conversations:
        try:
            summary_store.get(user_id, conversation.id)
            summary_count += 1
        except ConversationSummaryNotFoundError:
            continue
    return AnonymousDataSummary(
        has_data=bool(conversations or trip_plans or summary_count),
        conversations=len(conversations),
        conversation_summaries=summary_count,
        trip_plans=len(trip_plans),
    )


def _clone_user_data_for_import(source_user_id: str, target_user: AuthUser) -> UserDataImportRequest:
    source_user = AuthUser(
        id=source_user_id,
        email=f"{source_user_id}@anonymous.local",
        display_name="Anonymous traveler",
        created_at=datetime.now(UTC),
    )
    exported = _export_user_data(source_user_id, source_user)
    conversation_id_map: dict[str, str] = {}

    cloned_conversations = []
    for conversation in exported.conversations:
        new_conversation_id = str(uuid4())
        conversation_id_map[conversation.id] = new_conversation_id
        cloned_conversations.append(
            conversation.model_copy(
                update={
                    "id": new_conversation_id,
                    "messages": [message.model_copy(update={"id": str(uuid4())}) for message in conversation.messages],
                }
            )
        )

    cloned_summaries = [
        summary.model_copy(
            update={
                "id": str(uuid4()),
                "conversation_id": conversation_id_map[summary.conversation_id],
            }
        )
        for summary in exported.conversation_summaries
        if summary.conversation_id in conversation_id_map
    ]
    cloned_trip_plans = []
    for trip_plan in exported.trip_plans:
        new_trip_plan_id = str(uuid4())
        new_conversation_id = conversation_id_map.get(trip_plan.conversation_id or "")
        cloned_trip_plans.append(
            trip_plan.model_copy(
                update={
                    "id": new_trip_plan_id,
                    "conversation_id": new_conversation_id,
                    "plan": trip_plan.plan.model_copy(
                        update={
                            "saved_trip_plan_id": new_trip_plan_id,
                            "conversation_id": new_conversation_id,
                        }
                    ),
                }
            )
        )

    target_profile = profile_store.get(target_user.id)
    source_profile = exported.profile
    profile = source_profile if _profile_has_values(source_profile) and not _profile_has_values(target_profile) else target_profile

    return UserDataImportRequest(
        exported_at=datetime.now(UTC),
        user=target_user,
        profile=profile,
        conversations=cloned_conversations,
        conversation_summaries=cloned_summaries,
        trip_plans=cloned_trip_plans,
    )


def _profile_has_values(profile: UserProfile) -> bool:
    return bool(
        profile.display_name
        or profile.home_city
        or profile.preferred_budget
        or profile.travel_style
        or profile.interests
    )


def _redact_user_id(user_id: str) -> str:
    if len(user_id) <= 12:
        return user_id
    return f"{user_id[:8]}...{user_id[-4:]}"


def _travel_tool_catalog() -> dict[str, object]:
    tools = [tool.to_dict() for tool in travel_tool_provider.list_tools()]
    return {
        "provider": travel_tool_provider.name,
        "toolCount": len(tools),
        "tools": tools,
    }


def _agent_diagnostic_checks(
    capabilities: object,
    total_runs: int,
    quality_summary: object,
    tool_catalog: dict[str, object],
) -> list[dict[str, str]]:
    workflow_nodes = getattr(capabilities, "workflow_nodes", ())
    scored_runs = int(getattr(quality_summary, "scored_runs", 0))
    latest_grade = str(getattr(quality_summary, "latest_grade", ""))
    latest_score = getattr(quality_summary, "latest_score", None)
    checks = [
        {
            "name": "runtime",
            "status": "OK",
            "detail": "Agent runtime process is reachable.",
        },
        {
            "name": "engine",
            "status": "OK",
            "detail": f"{travel_agent_service.engine_name} is active.",
        },
        {
            "name": "workflow",
            "status": "OK" if workflow_nodes else "FAILED",
            "detail": f"{len(workflow_nodes)} workflow nodes registered.",
        },
        {
            "name": "llm",
            "status": "OK" if travel_agent_service.llm_enabled else "DEGRADED",
            "detail": (
                "LLM provider is configured."
                if travel_agent_service.llm_enabled
                else "LLM is disabled; fallback generation is active."
            ),
        },
        {
            "name": "travel_tools",
            "status": _travel_tools_diagnostic_status(str(tool_catalog["provider"]), int(tool_catalog["toolCount"])),
            "detail": _travel_tools_diagnostic_detail(str(tool_catalog["provider"]), int(tool_catalog["toolCount"])),
        },
        {
            "name": "trace_history",
            "status": "OK" if total_runs > 0 else "DISABLED",
            "detail": (
                f"{total_runs} recent agent runs recorded."
                if total_runs > 0
                else "No agent run has been recorded since startup."
            ),
        },
        {
            "name": "plan_quality",
            "status": _plan_quality_diagnostic_status(scored_runs, latest_grade),
            "detail": _plan_quality_diagnostic_detail(scored_runs, latest_grade, latest_score),
        },
    ]
    return checks


def _plan_quality_diagnostic_status(scored_runs: int, latest_grade: str) -> str:
    if scored_runs <= 0:
        return "DISABLED"
    if latest_grade == "ready":
        return "OK"
    return "DEGRADED"


def _plan_quality_diagnostic_detail(scored_runs: int, latest_grade: str, latest_score: object) -> str:
    if scored_runs <= 0:
        return "No trip plan quality score has been recorded since startup."
    return f"{scored_runs} scored trip plan runs; latest grade {latest_grade or 'unknown'} score {latest_score}."


def _travel_tools_diagnostic_status(provider: str, tool_count: int) -> str:
    if tool_count <= 0:
        return "FAILED"
    if provider == "mock" or provider.startswith("mock:"):
        return "DEGRADED"
    return "OK"


def _travel_tools_diagnostic_detail(provider: str, tool_count: int) -> str:
    if tool_count <= 0:
        return "No travel tools are registered."
    if provider == "mock" or provider.startswith("mock:"):
        return f"{tool_count} mock travel tools are registered; real provider integration is pending."
    return f"{tool_count} travel tools are registered."


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
