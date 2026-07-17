import re
import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime

from fastapi import Request


USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
AUTH_COOKIE_NAME = "travel_agent_session"
AUTHORIZATION_BEARER_PREFIX = "Bearer "
JWT_ALGORITHM = "HS256"
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "travel-agent-cloud-local-dev-secret")


def local_anonymous_user_id(request: Request) -> str | None:
    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id or user_id == "anonymous" or not USER_ID_PATTERN.fullmatch(user_id):
        return None
    return user_id


def current_user_id(request: Request) -> str | None:
    token = _session_token(request)
    if token:
        user_id = _verify_access_token(token)
        if user_id:
            return user_id
    return local_anonymous_user_id(request)


def _session_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith(AUTHORIZATION_BEARER_PREFIX):
        return authorization[len(AUTHORIZATION_BEARER_PREFIX) :].strip()
    return request.cookies.get(AUTH_COOKIE_NAME)


def _verify_access_token(token: str) -> str | None:
    try:
        header_text, payload_text, signature = token.split(".", 2)
        signing_input = f"{header_text}.{payload_text}"
        expected_signature = _sign(signing_input)
        if not hmac.compare_digest(signature, expected_signature):
            return None
        header = json.loads(_b64url_decode(header_text))
        payload = json.loads(_b64url_decode(payload_text))
    except (ValueError, json.JSONDecodeError):
        return None
    if header.get("alg") != JWT_ALGORITHM:
        return None
    subject = payload.get("sub")
    expires_at = payload.get("exp")
    if not isinstance(subject, str) or not isinstance(expires_at, int):
        return None
    if expires_at <= int(datetime.now(UTC).timestamp()):
        return None
    return subject


def _sign(signing_input: str) -> str:
    digest = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
