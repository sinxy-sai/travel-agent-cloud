import os
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from travel_common.app import add_cors, allowed_origins_from_env
from travel_common.internal_auth import (
    InternalServiceAuthMiddleware,
    RequestContextMiddleware,
    internal_service_headers,
    internal_service_token,
)
from travel_common.proxy import check_upstream, proxy_request

from app.account_data import AccountDataStore
from app.auth import (
    AUTH_COOKIE_NAME,
    AuthSettings,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    UserNotFoundError,
    UserStore,
    create_access_token,
    verify_access_token_claims,
)
from app.auth_identities import AuthIdentityConflictError, AuthIdentityNotFoundError, AuthIdentityStore
from app.auth_tokens import (
    TOKEN_PURPOSE_EMAIL_VERIFICATION,
    TOKEN_PURPOSE_PASSWORD_RESET,
    AuthTokenStore,
    InvalidAuthTokenError,
)
from app.db import create_session_factory
from app.mailer import Mailer, MailerSettings
from app.oauth import (
    GITHUB_PROVIDER,
    OAUTH_STATE_COOKIE_NAME,
    OAUTH_STATE_TTL_SECONDS,
    GitHubOAuthClient,
    OAuthConfigurationError,
    OAuthProfile,
    OAuthProviderError,
    OAuthSettings,
    OAuthStateError,
    create_oauth_state,
    verify_oauth_state,
)
from app.object_storage import MinioObjectStorage, ObjectStorageError, ObjectStorageNotFoundError, ObjectStorageSettings
from app.profiles import UserProfileStore
from app.schemas import (
    AnonymousDataSummary,
    AuthAccountDeleteRequest,
    AuthEmailActionResponse,
    AuthEmailRequest,
    AuthIdentityListResponse,
    AuthLoginRequest,
    AuthPasswordChangeRequest,
    AuthPasswordResetConfirmRequest,
    AuthRegisterRequest,
    AuthSession,
    AuthSessionListResponse,
    AuthSessionRevokeAllResponse,
    AuthTokenConfirmRequest,
    AuthUser,
    AuthUserUpdateRequest,
    UserDataExport,
    UserDataImportRequest,
    UserDataImportResponse,
    UserExportFile,
    UserSecurityEventListResponse,
    UserProfile,
    UserProfileUpdateRequest,
)
from app.security import FixedWindowRateLimiter, UserSecurityEventStore, client_identifier
from app.sessions import AuthSessionNotFoundError, AuthSessionRevokedError, AuthSessionStore
from app.users import local_anonymous_user_id


APP_NAME = "Travel Auth Service"
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("AUTH_SERVICE_REQUEST_TIMEOUT_SECONDS", "180"))
ALLOWED_ORIGINS = allowed_origins_from_env()
INTERNAL_SERVICE_TOKEN = internal_service_token()
INTERNAL_SERVICE_HEADERS = internal_service_headers(INTERNAL_SERVICE_TOKEN)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
auth_settings = AuthSettings(
    auth_secret_key=os.getenv("AUTH_SECRET_KEY", "travel-agent-cloud-local-dev-secret"),
    auth_token_ttl_seconds=int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(60 * 60 * 24 * 7))),
    auth_cookie_secure=os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"},
)
oauth_settings = OAuthSettings(
    auth_secret_key=auth_settings.auth_secret_key,
    github_oauth_client_id=os.getenv("GITHUB_OAUTH_CLIENT_ID", "").strip(),
    github_oauth_client_secret=os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "").strip(),
    github_oauth_redirect_uri=os.getenv(
        "GITHUB_OAUTH_REDIRECT_URI",
        "http://localhost:8300/api/v1/auth/oauth/github/callback",
    ).strip(),
    oauth_http_timeout_seconds=float(os.getenv("OAUTH_HTTP_TIMEOUT_SECONDS", "10")),
)
auth_rate_limiter = FixedWindowRateLimiter(
    int(os.getenv("AUTH_RATE_LIMIT_MAX_ATTEMPTS", "20")),
    int(os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", str(15 * 60))),
)
email_verification_token_ttl_seconds = int(os.getenv("EMAIL_VERIFICATION_TOKEN_TTL_SECONDS", str(60 * 60 * 24)))
password_reset_token_ttl_seconds = int(os.getenv("PASSWORD_RESET_TOKEN_TTL_SECONDS", str(60 * 30)))
email_provider = os.getenv("EMAIL_PROVIDER", "mock").strip().lower()
public_app_url = os.getenv("PUBLIC_APP_URL", "http://localhost:5173")
mailer = Mailer(
    MailerSettings(
        email_provider=email_provider,
        email_from=os.getenv("EMAIL_FROM", "no-reply@travel-agent-cloud.local").strip(),
        public_app_url=public_app_url,
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_use_ssl=os.getenv("SMTP_USE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"},
        smtp_starttls=os.getenv("SMTP_STARTTLS", "true").strip().lower() in {"1", "true", "yes", "on"},
    )
)
object_storage_settings = ObjectStorageSettings(
    minio_endpoint=os.getenv("MINIO_ENDPOINT", "").strip(),
    minio_access_key=os.getenv("MINIO_ACCESS_KEY", "").strip(),
    minio_secret_key=os.getenv("MINIO_SECRET_KEY", "").strip(),
    minio_bucket=os.getenv("MINIO_BUCKET", "travel-agent-exports").strip(),
    minio_secure=os.getenv("MINIO_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"},
)
session_factory = create_session_factory(DATABASE_URL) if DATABASE_URL else None
profile_store = UserProfileStore(session_factory) if session_factory else None
user_store = UserStore(session_factory) if session_factory else None
auth_session_store = AuthSessionStore(session_factory) if session_factory else None
security_event_store = UserSecurityEventStore(session_factory) if session_factory else None
auth_token_store = AuthTokenStore(session_factory) if session_factory else None
auth_identity_store = AuthIdentityStore(session_factory) if session_factory else None
github_oauth_client = GitHubOAuthClient(oauth_settings)
account_data_store = AccountDataStore(session_factory) if session_factory else None
object_storage = MinioObjectStorage(object_storage_settings)

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
        "status": "ok" if upstream["ok"] and profile_store is not None else "degraded",
        "service": APP_NAME,
        "mode": "auth-api-service-with-runtime-fallback",
        "databaseEnabled": profile_store is not None,
        "localAuthEnabled": _local_auth_enabled(),
        "githubOAuthEnabled": github_oauth_client.enabled,
        "objectStorageEnabled": object_storage.enabled,
        "upstreams": {"agentRuntime": upstream},
    }


@app.post("/api/v1/auth/register", response_model=AuthSession, status_code=status.HTTP_201_CREATED)
async def register(payload: AuthRegisterRequest, request: Request, response: Response) -> Any:
    if not _local_auth_enabled():
        return await _proxy(request, "/api/v1/auth/register")
    _check_auth_rate_limit(request, "register", payload.email)
    try:
        user = user_store.create_user(payload.email, payload.password, payload.display_name)  # type: ignore[union-attr]
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "EMAIL_ALREADY_REGISTERED", "message": "Email is already registered"},
        ) from exc
    session_info = _create_auth_session(request, user)
    token = create_access_token(auth_settings, user.id, session_info.id)
    _set_auth_cookie(response, token)
    _record_security_event(request, user.id, "auth.registered")
    return AuthSession(user=user)


@app.post("/api/v1/auth/login", response_model=AuthSession)
async def login(payload: AuthLoginRequest, request: Request, response: Response) -> Any:
    if not _local_auth_enabled():
        return await _proxy(request, "/api/v1/auth/login")
    _check_auth_rate_limit(request, "login", payload.email)
    try:
        user = user_store.authenticate(payload.email, payload.password)  # type: ignore[union-attr]
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"},
        ) from exc
    session_info = _create_auth_session(request, user)
    token = create_access_token(auth_settings, user.id, session_info.id)
    _set_auth_cookie(response, token)
    _record_security_event(request, user.id, "auth.logged_in")
    return AuthSession(user=user)


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> Response:
    if _local_auth_enabled():
        try:
            user = _get_current_auth_user(request)
            session_id = _get_current_auth_session_id(request)
            if session_id:
                auth_session_store.revoke(user.id, session_id)  # type: ignore[union-attr]
                _record_security_event(request, user.id, "auth.session_revoked", {"current": True})
            _record_security_event(request, user.id, "auth.logged_out")
        except HTTPException:
            pass
    response.status_code = status.HTTP_204_NO_CONTENT
    _delete_auth_cookie(response)
    return response


@app.get("/api/v1/auth/me", response_model=AuthUser)
async def get_current_auth_user(request: Request) -> Any:
    if not _local_auth_enabled():
        return await _proxy(request, "/api/v1/auth/me")
    return _get_current_auth_user(request)


@app.patch("/api/v1/auth/me", response_model=AuthUser)
async def update_current_auth_user(payload: AuthUserUpdateRequest, request: Request) -> Any:
    if not _local_auth_enabled():
        return await _proxy(request, "/api/v1/auth/me")
    user = _get_current_auth_user(request)
    try:
        updated = user_store.update_user(user.id, payload.display_name)  # type: ignore[union-attr]
    except UserNotFoundError as exc:
        raise _not_authenticated(exc)
    _record_security_event(request, user.id, "auth.user_updated")
    return updated


@app.patch("/api/v1/auth/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(payload: AuthPasswordChangeRequest, request: Request) -> Response:
    if not _local_auth_enabled():
        return await _proxy(request, "/api/v1/auth/password")
    user = _get_current_auth_user(request)
    _check_auth_rate_limit(request, "change-password", user.id)
    try:
        user_store.change_password(user.id, payload.current_password, payload.new_password)  # type: ignore[union-attr]
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Current password is incorrect"},
        ) from exc
    except UserNotFoundError as exc:
        raise _not_authenticated(exc)
    _record_security_event(request, user.id, "auth.password_changed")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/auth/sessions", response_model=AuthSessionListResponse)
async def list_current_auth_sessions(request: Request) -> Any:
    if not _local_auth_enabled():
        return await _proxy(request, "/api/v1/auth/sessions")
    user = _get_current_auth_user(request)
    current_session_id = _get_current_auth_session_id(request)
    return AuthSessionListResponse(
        data=auth_session_store.list_for_user(user.id, current_session_id)  # type: ignore[union-attr]
    )


@app.post("/api/v1/auth/sessions/revoke-all", response_model=AuthSessionRevokeAllResponse)
async def revoke_other_auth_sessions(request: Request) -> Any:
    if not _local_auth_enabled():
        return await _proxy(request, "/api/v1/auth/sessions/revoke-all")
    user = _get_current_auth_user(request)
    current_session_id = _get_current_auth_session_id(request)
    revoked = auth_session_store.revoke_all(user.id, except_session_id=current_session_id)  # type: ignore[union-attr]
    _record_security_event(request, user.id, "auth.sessions_revoked_all", {"revoked": revoked})
    return AuthSessionRevokeAllResponse(revoked=revoked)


@app.delete("/api/v1/auth/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_current_auth_session(session_id: str, request: Request, response: Response) -> Response:
    if not _local_auth_enabled():
        return await _proxy(request, f"/api/v1/auth/sessions/{session_id}")
    user = _get_current_auth_user(request)
    current_session_id = _get_current_auth_session_id(request)
    try:
        auth_session_store.revoke(user.id, session_id)  # type: ignore[union-attr]
    except AuthSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "Auth session not found"},
        ) from exc
    _record_security_event(request, user.id, "auth.session_revoked", {"current": session_id == current_session_id})
    response.status_code = status.HTTP_204_NO_CONTENT
    if session_id == current_session_id:
        _delete_auth_cookie(response)
    return response


@app.api_route(
    "/api/v1/auth/email-verification/request",
    methods=["POST"],
)
async def request_email_verification(request: Request) -> AuthEmailActionResponse:
    user = _get_current_auth_user(request)
    if user.email_verified:
        return AuthEmailActionResponse(sent=False, delivery="already_verified")
    generated = auth_token_store.create(  # type: ignore[union-attr]
        user.id,
        TOKEN_PURPOSE_EMAIL_VERIFICATION,
        email_verification_token_ttl_seconds,
    )
    delivery = mailer.send_email_verification(user.email, generated.token)
    response = AuthEmailActionResponse(sent=delivery.sent, delivery=delivery.delivery, expires_at=generated.expires_at)
    if email_provider in {"", "mock"}:
        response.dev_token = generated.token
        response.action_url = mailer.verification_url(generated.token)
    _record_security_event(request, user.id, "auth.email_verification_requested", {"delivery": response.delivery})
    return response


@app.post("/api/v1/auth/email-verification/confirm", response_model=AuthUser)
async def confirm_email_verification(payload: AuthTokenConfirmRequest, request: Request) -> AuthUser:
    try:
        user_id = auth_token_store.consume(payload.token, TOKEN_PURPOSE_EMAIL_VERIFICATION)  # type: ignore[union-attr]
        user = user_store.mark_email_verified(user_id)  # type: ignore[union-attr]
    except (InvalidAuthTokenError, UserNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TOKEN", "message": "Verification link is invalid or expired"},
        ) from exc
    _record_security_event(request, user.id, "auth.email_verified")
    return user


@app.api_route(
    "/api/v1/auth/email-verification/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_email_verification(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/auth/email-verification/{path}")


@app.post("/api/v1/auth/password-reset/request", response_model=AuthEmailActionResponse)
async def request_password_reset(payload: AuthEmailRequest, request: Request) -> AuthEmailActionResponse:
    _check_auth_rate_limit(request, "password-reset", payload.email)
    try:
        user = user_store.get_user_by_email(payload.email)  # type: ignore[union-attr]
    except (UserNotFoundError, ValueError):
        return AuthEmailActionResponse(sent=True, delivery="accepted")
    generated = auth_token_store.create(  # type: ignore[union-attr]
        user.id,
        TOKEN_PURPOSE_PASSWORD_RESET,
        password_reset_token_ttl_seconds,
    )
    delivery = mailer.send_password_reset(user.email, generated.token)
    response = AuthEmailActionResponse(sent=delivery.sent, delivery=delivery.delivery, expires_at=generated.expires_at)
    if email_provider in {"", "mock"}:
        response.dev_token = generated.token
        response.action_url = mailer.password_reset_url(generated.token)
    _record_security_event(request, user.id, "auth.password_reset_requested", {"delivery": response.delivery})
    return response


@app.post("/api/v1/auth/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(payload: AuthPasswordResetConfirmRequest, request: Request) -> Response:
    try:
        user_id = auth_token_store.consume(payload.token, TOKEN_PURPOSE_PASSWORD_RESET)  # type: ignore[union-attr]
        user_store.reset_password(user_id, payload.new_password)  # type: ignore[union-attr]
        revoked = auth_session_store.revoke_all(user_id)  # type: ignore[union-attr]
    except (InvalidAuthTokenError, UserNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TOKEN", "message": "Password reset link is invalid or expired"},
        ) from exc
    _record_security_event(request, user_id, "auth.password_reset_completed")
    if revoked:
        _record_security_event(request, user_id, "auth.sessions_revoked_all", {"revoked": revoked})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.api_route(
    "/api/v1/auth/password-reset/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_password_reset(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/auth/password-reset/{path}")


@app.get("/api/v1/auth/oauth/github/start")
def start_github_oauth() -> RedirectResponse:
    try:
        state_value = create_oauth_state(oauth_settings, GITHUB_PROVIDER)
        redirect = RedirectResponse(github_oauth_client.authorization_url(state_value), status_code=status.HTTP_302_FOUND)
    except OAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OAUTH_PROVIDER_DISABLED", "message": "GitHub OAuth is not configured"},
        ) from exc
    _set_oauth_state_cookie(redirect, state_value)
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
        verify_oauth_state(oauth_settings, state, GITHUB_PROVIDER)
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
    token = create_access_token(auth_settings, user.id, session_info.id)
    redirect = _oauth_frontend_redirect("success")
    _set_auth_cookie(redirect, token)
    _delete_oauth_state_cookie(redirect)
    _record_security_event(request, user.id, event_type, {"provider": GITHUB_PROVIDER})
    return redirect


@app.api_route(
    "/api/v1/auth/oauth/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_oauth(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/auth/oauth/{path}")


@app.get("/api/v1/auth/identities", response_model=AuthIdentityListResponse)
async def list_current_auth_identities(request: Request) -> AuthIdentityListResponse:
    user = _get_current_auth_user(request)
    return AuthIdentityListResponse(data=auth_identity_store.list_for_user(user.id))  # type: ignore[union-attr]


@app.api_route("/api/v1/auth/identities/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_auth_identities(path: str, request: Request) -> Response:
    if request.method == "DELETE":
        user = _get_current_auth_user(request)
        try:
            auth_identity_store.delete_for_user(user.id, path)  # type: ignore[union-attr]
        except AuthIdentityNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "IDENTITY_NOT_FOUND", "message": "Auth identity not found"},
            ) from exc
        _record_security_event(request, user.id, "auth.identity_unlinked", {"provider": path})
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return await _proxy(request, f"/api/v1/auth/identities/{path}")


@app.get("/api/v1/auth/security-events", response_model=UserSecurityEventListResponse)
async def list_current_security_events(
    request: Request,
    page: int = 1,
    pageSize: int = 10,
) -> UserSecurityEventListResponse:
    user = _get_current_auth_user(request)
    return security_event_store.list(user.id, page, pageSize)  # type: ignore[union-attr]


@app.delete("/api/v1/auth/me")
async def delete_current_auth_user(payload: AuthAccountDeleteRequest, request: Request, response: Response) -> Response:
    user = _get_current_auth_user(request)
    _check_auth_rate_limit(request, "delete-account", user.id)
    try:
        user_store.delete_user(user.id, payload.current_password)  # type: ignore[union-attr]
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Current password is incorrect"},
        ) from exc
    except UserNotFoundError as exc:
        raise _not_authenticated(exc)
    if object_storage.enabled:
        try:
            object_storage.delete_user_exports(user.id)
        except ObjectStorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "OBJECT_STORAGE_UNAVAILABLE", "message": "Could not delete stored export files"},
            ) from exc
    response.status_code = status.HTTP_204_NO_CONTENT
    _delete_auth_cookie(response)
    return response


@app.get("/api/v1/me/export", response_model=UserDataExport)
async def export_current_user_data_unverified_guard(request: Request) -> UserDataExport:
    user = _get_current_auth_user(request)
    if not user.email_verified:
        raise _email_not_verified()
    _require_account_data_store()
    exported = account_data_store.export_user_data(user.id, user)  # type: ignore[union-attr]
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
async def create_current_user_export_file(request: Request) -> UserExportFile:
    user = _get_current_auth_user(request)
    if not user.email_verified:
        raise _email_not_verified()
    _require_account_data_store()
    if not object_storage.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "OBJECT_STORAGE_DISABLED", "message": "Object storage is not configured"},
        )
    exported = account_data_store.export_user_data(user.id, user)  # type: ignore[union-attr]
    payload = json.dumps(exported.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2).encode("utf-8")
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
async def download_current_user_export_file(export_id: UUID, request: Request) -> Response:
    user = _get_current_auth_user(request)
    if not user.email_verified:
        raise _email_not_verified()
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
async def import_current_user_data(payload: UserDataImportRequest, request: Request) -> UserDataImportResponse:
    user = _get_current_auth_user(request)
    if not user.email_verified:
        raise _email_not_verified()
    _check_auth_rate_limit(request, "import-data", user.id)
    _require_account_data_store()
    result = account_data_store.import_user_data(user.id, payload)  # type: ignore[union-attr]
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
    return result


@app.get("/api/v1/me/anonymous-data/summary", response_model=AnonymousDataSummary)
async def summarize_current_anonymous_data(request: Request) -> AnonymousDataSummary:
    _get_current_auth_user(request)
    anonymous_user_id = local_anonymous_user_id(request)
    if not anonymous_user_id:
        return AnonymousDataSummary(has_data=False, conversations=0, conversation_summaries=0, trip_plans=0)
    _require_account_data_store()
    return account_data_store.summarize_anonymous_data(anonymous_user_id)  # type: ignore[union-attr]


@app.post("/api/v1/me/anonymous-data/import", response_model=UserDataImportResponse)
async def import_current_anonymous_data(request: Request) -> UserDataImportResponse:
    user = _get_current_auth_user(request)
    if not user.email_verified:
        raise _email_not_verified()
    anonymous_user_id = local_anonymous_user_id(request)
    if not anonymous_user_id or anonymous_user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_ANONYMOUS_USER", "message": "Anonymous user id must be different from account id"},
        )
    _require_account_data_store()
    payload = account_data_store.clone_user_data_for_import(anonymous_user_id, user)  # type: ignore[union-attr]
    result = account_data_store.import_user_data(user.id, payload)  # type: ignore[union-attr]
    _record_security_event(
        request,
        user.id,
        "user.anonymous_data_imported",
        {
            "sourceUserId": _redact_id(anonymous_user_id),
            "conversationsImported": result.conversations_imported,
            "conversationSummariesImported": result.conversation_summaries_imported,
            "tripPlansImported": result.trip_plans_imported,
            "skippedItems": result.skipped_items,
        },
    )
    return result


@app.api_route("/api/v1/me", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_me_root(request: Request) -> Response:
    return await _proxy(request, "/api/v1/me")


@app.get("/api/v1/me/profile", response_model=UserProfile)
async def get_profile(request: Request) -> Any:
    user_id = _optional_auth_user_id(request) or local_anonymous_user_id(request)
    if not user_id or not profile_store:
        return await _proxy(request, "/api/v1/me/profile")
    return profile_store.get(user_id)


@app.patch("/api/v1/me/profile", response_model=UserProfile)
async def update_profile(payload: UserProfileUpdateRequest, request: Request) -> Any:
    user_id = _optional_auth_user_id(request) or local_anonymous_user_id(request)
    if not user_id or not profile_store:
        return await _proxy(request, "/api/v1/me/profile")
    profile = profile_store.update(user_id, payload)
    _record_security_event(request, user_id, "user.profile.updated", {"updatedFields": sorted(payload.model_fields_set)})
    return profile


@app.api_route("/api/v1/me/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_me(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/me/{path}")


@app.api_route("/api/v1/auth", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_auth_root(request: Request) -> Response:
    return await _proxy(request, "/api/v1/auth")


@app.api_route("/api/v1/auth/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_auth(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/auth/{path}")


async def _proxy(request: Request, path: str) -> Response:
    return await proxy_request(
        request,
        upstream_base_url=AGENT_RUNTIME_URL,
        path=path,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        service_boundary="travel-auth",
        extra_headers=_runtime_auth_headers(request),
    )


def _local_auth_enabled() -> bool:
    return bool(
        user_store
        and auth_session_store
        and profile_store
        and security_event_store
        and auth_token_store
        and auth_identity_store
    )


def _create_auth_session(request: Request, user: AuthUser):
    expires_at = datetime.now(UTC) + timedelta(seconds=auth_settings.auth_token_ttl_seconds)
    session_info = auth_session_store.create(  # type: ignore[union-attr]
        user.id,
        expires_at,
        client_identifier=client_identifier(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    _record_security_event(request, user.id, "auth.session_created", {"sessionId": _redact_id(session_info.id)})
    return session_info


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=auth_settings.auth_token_ttl_seconds,
        httponly=True,
        secure=auth_settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _delete_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=auth_settings.auth_cookie_secure,
    )


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :].strip()
    return None


def _runtime_auth_headers(request: Request) -> dict[str, str]:
    headers = dict(INTERNAL_SERVICE_HEADERS)
    if request.headers.get("Authorization"):
        return headers
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return headers
    headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_current_auth_claims(request: Request):
    token = request.cookies.get(AUTH_COOKIE_NAME) or _bearer_token(request)
    if not token:
        raise _not_authenticated()

    try:
        claims = verify_access_token_claims(auth_settings, token)
        if claims.session_id:
            auth_session_store.require_active(claims.user_id, claims.session_id)  # type: ignore[union-attr]
        return claims
    except (InvalidCredentialsError, AuthSessionNotFoundError, AuthSessionRevokedError) as exc:
        raise _not_authenticated(exc)


def _get_current_auth_user(request: Request) -> AuthUser:
    claims = _get_current_auth_claims(request)
    try:
        return user_store.get_user(claims.user_id)  # type: ignore[union-attr]
    except UserNotFoundError as exc:
        raise _not_authenticated(exc)


def _get_current_auth_session_id(request: Request) -> str | None:
    return _get_current_auth_claims(request).session_id


def _optional_auth_user_id(request: Request) -> str | None:
    if not _local_auth_enabled():
        return None
    try:
        return _get_current_auth_user(request).id
    except HTTPException:
        return None


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


def _resolve_oauth_user(request: Request, profile: OAuthProfile) -> tuple[AuthUser, str]:
    current_user = _get_optional_current_auth_user(request)
    try:
        identity = auth_identity_store.get_by_provider_user_id(profile.provider, profile.provider_user_id)  # type: ignore[union-attr]
        if current_user and identity.user_id != current_user.id:
            raise AuthIdentityConflictError(profile.provider)
        user = user_store.get_user(identity.user_id)  # type: ignore[union-attr]
        auth_identity_store.upsert(  # type: ignore[union-attr]
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
        auth_identity_store.upsert(  # type: ignore[union-attr]
            current_user.id,
            profile.provider,
            profile.provider_user_id,
            email=profile.email,
            display_name=profile.display_name,
            avatar_url=profile.avatar_url,
        )
        return current_user, "auth.identity_linked"

    try:
        user = user_store.get_user_by_email(profile.email)  # type: ignore[union-attr]
        if not user.email_verified:
            user = user_store.mark_email_verified(user.id)  # type: ignore[union-attr]
    except UserNotFoundError:
        try:
            user = user_store.create_oauth_user(profile.email, profile.display_name)  # type: ignore[union-attr]
        except EmailAlreadyRegisteredError:
            user = user_store.get_user_by_email(profile.email)  # type: ignore[union-attr]
            if not user.email_verified:
                user = user_store.mark_email_verified(user.id)  # type: ignore[union-attr]

    auth_identity_store.upsert(  # type: ignore[union-attr]
        user.id,
        profile.provider,
        profile.provider_user_id,
        email=profile.email,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
    )
    return user, "auth.oauth_logged_in"


def _get_optional_current_auth_user(request: Request) -> AuthUser | None:
    try:
        return _get_current_auth_user(request)
    except HTTPException:
        return None


def _oauth_frontend_redirect(status_value: str, error: str = "") -> RedirectResponse:
    params = {"authAction": "oauth-github", "authStatus": status_value}
    if error:
        params["authError"] = error
    return RedirectResponse(
        f"{public_app_url.rstrip('/')}?{urlencode(params)}",
        status_code=status.HTTP_302_FOUND,
    )


def _set_oauth_state_cookie(response: Response, state_value: str) -> None:
    response.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        state_value,
        max_age=OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=auth_settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _delete_oauth_state_cookie(response: Response) -> None:
    response.delete_cookie(
        OAUTH_STATE_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=auth_settings.auth_cookie_secure,
    )


def _record_security_event(
    request: Request,
    user_id: str,
    event_type: str,
    details: dict | None = None,
) -> None:
    if not security_event_store:
        return
    security_event_store.record(
        user_id,
        event_type,
        client_identifier=client_identifier(request),
        details=details,
    )


def _not_authenticated(exc: Exception | None = None) -> HTTPException:
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
    )
    if exc is not None:
        return error
    return error


def _email_not_verified() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "EMAIL_NOT_VERIFIED", "message": "Verify your email before managing account data"},
    )


def _require_account_data_store() -> None:
    if account_data_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DATABASE_DISABLED", "message": "Database is not configured"},
        )


def _redact_id(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"
