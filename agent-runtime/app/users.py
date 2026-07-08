import re

from fastapi import Header

USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
DEFAULT_USER_ID = "anonymous"


def get_user_id(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> str:
    if not x_user_id:
        return DEFAULT_USER_ID

    normalized = x_user_id.strip()
    if not USER_ID_PATTERN.fullmatch(normalized):
        return DEFAULT_USER_ID
    return normalized
