import os
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request, Response, status
from travel_common.app import add_cors, allowed_origins_from_env
from travel_common.proxy import check_upstream, proxy_request

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
from app.auth_identities import AuthIdentityNotFoundError, AuthIdentityStore
from app.auth_tokens import (
    TOKEN_PURPOSE_EMAIL_VERIFICATION,
    TOKEN_PURPOSE_PASSWORD_RESET,
    AuthTokenStore,
    InvalidAuthTokenError,
)
from app.db import create_session_factory
from app.profiles import UserProfileStore
from app.schemas import (
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
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
auth_settings = AuthSettings(
    auth_secret_key=os.getenv("AUTH_SECRET_KEY", "travel-agent-cloud-local-dev-secret"),
    auth_token_ttl_seconds=int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(60 * 60 * 24 * 7))),
    auth_cookie_secure=os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"},
)
auth_rate_limiter = FixedWindowRateLimiter(
    int(os.getenv("AUTH_RATE_LIMIT_MAX_ATTEMPTS", "20")),
    int(os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", str(15 * 60))),
)
email_verification_token_ttl_seconds = int(os.getenv("EMAIL_VERIFICATION_TOKEN_TTL_SECONDS", str(60 * 60 * 24)))
password_reset_token_ttl_seconds = int(os.getenv("PASSWORD_RESET_TOKEN_TTL_SECONDS", str(60 * 30)))
email_provider = os.getenv("EMAIL_PROVIDER", "mock").strip().lower()
public_app_url = os.getenv("PUBLIC_APP_URL", "http://localhost:5173")
session_factory = create_session_factory(DATABASE_URL) if DATABASE_URL else None
profile_store = UserProfileStore(session_factory) if session_factory else None
user_store = UserStore(session_factory) if session_factory else None
auth_session_store = AuthSessionStore(session_factory) if session_factory else None
security_event_store = UserSecurityEventStore(session_factory) if session_factory else None
auth_token_store = AuthTokenStore(session_factory) if session_factory else None
auth_identity_store = AuthIdentityStore(session_factory) if session_factory else None

app = FastAPI(title=APP_NAME, version="0.1.0")
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
    response = AuthEmailActionResponse(sent=True, delivery=email_provider or "mock", expires_at=generated.expires_at)
    if email_provider in {"", "mock"}:
        response.dev_token = generated.token
        response.action_url = _action_url("verify-email", generated.token)
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
    response = AuthEmailActionResponse(sent=True, delivery=email_provider or "mock", expires_at=generated.expires_at)
    if email_provider in {"", "mock"}:
        response.dev_token = generated.token
        response.action_url = _action_url("reset-password", generated.token)
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
    response.status_code = status.HTTP_204_NO_CONTENT
    _delete_auth_cookie(response)
    return response


@app.get("/api/v1/me/export")
async def export_current_user_data_unverified_guard(request: Request) -> Any:
    user = _get_current_auth_user(request)
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "EMAIL_NOT_VERIFIED", "message": "Verify your email before managing account data"},
        )
    return await _proxy(request, "/api/v1/me/export")


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
    if request.headers.get("Authorization"):
        return {}
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


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


def _redact_id(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _action_url(action: str, token: str) -> str:
    return f"{public_app_url.rstrip('/')}?{urlencode({'authAction': action, 'token': token})}"
