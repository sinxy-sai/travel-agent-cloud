import re

from fastapi import Header, Request

from app.auth import AUTH_COOKIE_NAME, InvalidCredentialsError, verify_access_token
from app.settings import get_settings

AUTHORIZATION_BEARER_PREFIX = "Bearer "
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
DEFAULT_USER_ID = "anonymous"


def get_user_id(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    token = _session_token(request, authorization)
    if token:
        try:
            return verify_access_token(get_settings(), token)
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
