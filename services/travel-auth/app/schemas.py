from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AuthRegisterRequest(APIModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=80)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Password cannot start or end with whitespace")
        return value

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        return value.strip()


class AuthLoginRequest(APIModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthPasswordChangeRequest(APIModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Password cannot start or end with whitespace")
        return value


class AuthEmailRequest(APIModel):
    email: str = Field(min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthEmailActionResponse(APIModel):
    sent: bool
    delivery: str
    expires_at: datetime | None = None
    dev_token: str | None = None
    action_url: str | None = None


class AuthTokenConfirmRequest(APIModel):
    token: str = Field(min_length=20, max_length=300)


class AuthPasswordResetConfirmRequest(APIModel):
    token: str = Field(min_length=20, max_length=300)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Password cannot start or end with whitespace")
        return value


class AuthAccountDeleteRequest(APIModel):
    current_password: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=6, max_length=32)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        confirmation = value.strip().upper()
        if confirmation != "DELETE":
            raise ValueError("Confirmation must be DELETE")
        return confirmation


class AuthUserUpdateRequest(APIModel):
    display_name: str = Field(default="", max_length=80)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        return value.strip()


class AuthUser(APIModel):
    id: str
    email: str
    display_name: str = ""
    email_verified: bool = False
    password_configured: bool = True
    created_at: datetime


class AuthSession(APIModel):
    user: AuthUser


class AuthSessionInfo(APIModel):
    id: str
    user_id: str
    user_agent: str = ""
    current: bool = False
    revoked: bool = False
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


class AuthSessionListResponse(APIModel):
    data: list[AuthSessionInfo]


class AuthSessionRevokeAllResponse(APIModel):
    revoked: int


class AuthIdentity(APIModel):
    id: str
    user_id: str
    provider: str
    provider_user_id: str
    email: str = ""
    display_name: str = ""
    avatar_url: str = ""
    created_at: datetime


class AuthIdentityListResponse(APIModel):
    data: list[AuthIdentity]


class UserSecurityEvent(APIModel):
    id: str
    event_type: str
    details: dict = Field(default_factory=dict)
    created_at: datetime


class UserSecurityEventListResponse(APIModel):
    data: list[UserSecurityEvent]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class UserProfile(APIModel):
    user_id: str
    display_name: str = ""
    home_city: str = ""
    preferred_budget: str = ""
    travel_style: str = ""
    interests: list[str] = Field(default_factory=list)
    updated_at: datetime


class UserProfileUpdateRequest(APIModel):
    display_name: str | None = Field(default=None, max_length=80)
    home_city: str | None = Field(default=None, max_length=80)
    preferred_budget: str | None = Field(default=None, max_length=40)
    travel_style: str | None = Field(default=None, max_length=80)
    interests: list[str] | None = Field(default=None, max_length=12)

    @field_validator("display_name", "home_city", "preferred_budget", "travel_style")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            interest = item.strip()
            if not interest or len(interest) > 40:
                continue
            key = interest.lower()
            if key not in seen:
                normalized.append(interest)
                seen.add(key)
        return normalized[:12]
