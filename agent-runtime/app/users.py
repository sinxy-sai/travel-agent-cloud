import re
import base64
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Header, Request

from app.settings import get_settings

AUTH_COOKIE_NAME = "travel_agent_session"
AUTHORIZATION_BEARER_PREFIX = "Bearer "
JWT_ALGORITHM = "HS256"
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
DEFAULT_USER_ID = "anonymous"


class InvalidCredentialsError(Exception):
    pass


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: str
    session_id: str | None = None


def get_user_id(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    token = _session_token(request, authorization)
    if token:
        try:
            return _verify_access_token(get_settings(), token)
        except InvalidCredentialsError:
            pass

    if not x_user_id:
        return DEFAULT_USER_ID

    normalized = x_user_id.strip()
    if not USER_ID_PATTERN.fullmatch(normalized):
        return DEFAULT_USER_ID
    return normalized


def _session_token(request: Request, authorization: str | None) -> str | None:
    if authorization and authorization.startswith(AUTHORIZATION_BEARER_PREFIX):
        return authorization[len(AUTHORIZATION_BEARER_PREFIX) :].strip()
    return request.cookies.get(AUTH_COOKIE_NAME)


def _verify_access_token(settings, token: str) -> str:
    return _verify_access_token_claims(settings, token).user_id


def _verify_access_token_claims(settings, token: str) -> AccessTokenClaims:
    try:
        header_text, payload_text, signature = token.split(".", 2)
    except ValueError as exc:
        raise InvalidCredentialsError() from exc

    signing_input = f"{header_text}.{payload_text}"
    expected_signature = _sign(settings.auth_secret_key, signing_input)
    if not hmac.compare_digest(signature, expected_signature):
        raise InvalidCredentialsError()

    try:
        header = json.loads(_b64url_decode(header_text))
        payload = json.loads(_b64url_decode(payload_text))
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidCredentialsError() from exc

    if header.get("alg") != JWT_ALGORITHM:
        raise InvalidCredentialsError()

    subject = payload.get("sub")
    session_id = payload.get("sid")
    expires_at = payload.get("exp")
    if not isinstance(subject, str) or not isinstance(expires_at, int):
        raise InvalidCredentialsError()
    if session_id is not None and not isinstance(session_id, str):
        raise InvalidCredentialsError()
    if expires_at <= int(datetime.now(UTC).timestamp()):
        raise InvalidCredentialsError()
    return AccessTokenClaims(user_id=subject, session_id=session_id)


def _sign(secret_key: str, signing_input: str) -> str:
    digest = hmac.new(secret_key.encode("utf-8"), signing_input.encode("utf-8"), "sha256").digest()
    return _b64url_encode(digest)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}".encode("ascii"))
