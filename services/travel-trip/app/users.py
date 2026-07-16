import re

from fastapi import Request


USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")


def local_anonymous_user_id(request: Request) -> str | None:
    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id or user_id == "anonymous" or not USER_ID_PATTERN.fullmatch(user_id):
        return None
    return user_id
