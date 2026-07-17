import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import AuthSessionRecord, UserProfileRecord, UserRecord, UserSecurityEventRecord
from app.schemas import AuthUser

AUTH_COOKIE_NAME = "travel_agent_session"
JWT_ALGORITHM = "HS256"
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 210_000
UNUSABLE_PASSWORD_HASH_PREFIX = "oauth_unset$"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidCredentialsError(Exception):
    pass


class EmailAlreadyRegisteredError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: str
    session_id: str | None = None


@dataclass(frozen=True)
class AuthSettings:
    auth_secret_key: str
    auth_token_ttl_seconds: int
    auth_cookie_secure: bool


class UserStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_user(self, email: str, password: str, display_name: str = "") -> AuthUser:
        normalized_email = _normalize_email(email)
        with session_scope(self._session_factory) as session:
            record = UserRecord(
                email=normalized_email,
                password_hash=hash_password(password),
                display_name=display_name.strip(),
            )
            session.add(record)
            try:
                session.flush()
            except IntegrityError as exc:
                raise EmailAlreadyRegisteredError(normalized_email) from exc
            return _to_auth_user(record)

    def create_oauth_user(self, email: str, display_name: str = "") -> AuthUser:
        normalized_email = _normalize_email(email)
        with session_scope(self._session_factory) as session:
            record = UserRecord(
                email=normalized_email,
                password_hash=f"{UNUSABLE_PASSWORD_HASH_PREFIX}{secrets.token_urlsafe(32)}",
                display_name=display_name.strip(),
                email_verified=True,
                email_verified_at=_now(),
            )
            session.add(record)
            try:
                session.flush()
            except IntegrityError as exc:
                raise EmailAlreadyRegisteredError(normalized_email) from exc
            return _to_auth_user(record)

    def authenticate(self, email: str, password: str) -> AuthUser:
        normalized_email = _normalize_email(email)
        with session_scope(self._session_factory) as session:
            record = session.scalar(select(UserRecord).where(UserRecord.email == normalized_email))
            if record is None or not verify_password(password, record.password_hash):
                raise InvalidCredentialsError()
            return _to_auth_user(record)

    def get_user(self, user_id: str) -> AuthUser:
        with session_scope(self._session_factory) as session:
            record = session.scalar(select(UserRecord).where(UserRecord.id == user_id))
            if record is None:
                raise UserNotFoundError(user_id)
            return _to_auth_user(record)

    def get_user_by_email(self, email: str) -> AuthUser:
        normalized_email = _normalize_email(email)
        with session_scope(self._session_factory) as session:
            record = session.scalar(select(UserRecord).where(UserRecord.email == normalized_email))
            if record is None:
                raise UserNotFoundError(normalized_email)
            return _to_auth_user(record)

    def update_user(self, user_id: str, display_name: str) -> AuthUser:
        with session_scope(self._session_factory) as session:
            record = session.scalar(select(UserRecord).where(UserRecord.id == user_id))
            if record is None:
                raise UserNotFoundError(user_id)
            record.display_name = display_name.strip()
            record.updated_at = _now()
            session.flush()
            return _to_auth_user(record)

    def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        with session_scope(self._session_factory) as session:
            record = session.scalar(select(UserRecord).where(UserRecord.id == user_id))
            if record is None:
                raise UserNotFoundError(user_id)
            if not verify_password(current_password, record.password_hash):
                raise InvalidCredentialsError()
            record.password_hash = hash_password(new_password)
            record.updated_at = _now()

    def reset_password(self, user_id: str, new_password: str) -> None:
        with session_scope(self._session_factory) as session:
            record = session.scalar(select(UserRecord).where(UserRecord.id == user_id))
            if record is None:
                raise UserNotFoundError(user_id)
            record.password_hash = hash_password(new_password)
            record.updated_at = _now()

    def mark_email_verified(self, user_id: str) -> AuthUser:
        with session_scope(self._session_factory) as session:
            record = session.scalar(select(UserRecord).where(UserRecord.id == user_id))
            if record is None:
                raise UserNotFoundError(user_id)
            record.email_verified = True
            record.email_verified_at = _now()
            record.updated_at = record.email_verified_at
            session.flush()
            return _to_auth_user(record)

    def delete_user(self, user_id: str, current_password: str) -> None:
        with session_scope(self._session_factory) as session:
            record = session.scalar(select(UserRecord).where(UserRecord.id == user_id))
            if record is None:
                raise UserNotFoundError(user_id)
            if not verify_password(current_password, record.password_hash):
                raise InvalidCredentialsError()
            session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.user_id == user_id))
            session.execute(delete(UserSecurityEventRecord).where(UserSecurityEventRecord.user_id == user_id))
            session.execute(delete(UserProfileRecord).where(UserProfileRecord.user_id == user_id))
            session.delete(record)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
    return "$".join(
        [
            PASSWORD_HASH_ALGORITHM,
            str(PASSWORD_HASH_ITERATIONS),
            _b64url_encode(salt),
            _b64url_encode(digest),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = _b64url_decode(salt_text)
        expected_digest = _b64url_decode(digest_text)
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(
    settings: AuthSettings,
    user_id: str,
    session_id: str | None = None,
    now: datetime | None = None,
) -> str:
    issued_at = now or _now()
    expires_at = issued_at + timedelta(seconds=settings.auth_token_ttl_seconds)
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload: dict[str, object] = {
        "sub": user_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if session_id:
        payload["sid"] = session_id
    signing_input = f"{_b64url_json(header)}.{_b64url_json(payload)}"
    signature = _sign(settings.auth_secret_key, signing_input)
    return f"{signing_input}.{signature}"


def verify_access_token_claims(settings: AuthSettings, token: str, now: datetime | None = None) -> AccessTokenClaims:
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

    current_time = int((now or _now()).timestamp())
    if expires_at <= current_time:
        raise InvalidCredentialsError()
    return AccessTokenClaims(user_id=subject, session_id=session_id)


def is_password_configured(password_hash: str) -> bool:
    return not password_hash.startswith(UNUSABLE_PASSWORD_HASH_PREFIX)


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Valid email is required")
    return normalized


def _to_auth_user(record: UserRecord) -> AuthUser:
    return AuthUser(
        id=record.id,
        email=record.email,
        display_name=record.display_name,
        email_verified=record.email_verified,
        password_configured=is_password_configured(record.password_hash),
        created_at=record.created_at,
    )


def _sign(secret: str, signing_input: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def _b64url_json(payload: dict[str, object]) -> str:
    return _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _now() -> datetime:
    return datetime.now(UTC)
