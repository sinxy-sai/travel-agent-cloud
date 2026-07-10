import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.settings import Settings

GITHUB_PROVIDER = "github"
OAUTH_STATE_COOKIE_NAME = "travel_agent_oauth_state"
OAUTH_STATE_TTL_SECONDS = 10 * 60


class OAuthConfigurationError(Exception):
    pass


class OAuthProviderError(Exception):
    pass


class OAuthStateError(Exception):
    pass


@dataclass(frozen=True)
class OAuthProfile:
    provider: str
    provider_user_id: str
    email: str
    display_name: str = ""
    avatar_url: str = ""


class GitHubOAuthClient:
    authorize_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    user_url = "https://api.github.com/user"
    emails_url = "https://api.github.com/user/emails"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return bool(
            self._settings.github_oauth_client_id.strip()
            and self._settings.github_oauth_client_secret.strip()
            and self._settings.github_oauth_redirect_uri.strip()
        )

    def authorization_url(self, state: str) -> str:
        self._require_configured()
        params = {
            "client_id": self._settings.github_oauth_client_id,
            "redirect_uri": self._settings.github_oauth_redirect_uri,
            "scope": "read:user user:email",
            "state": state,
            "allow_signup": "true",
        }
        return f"{self.authorize_url}?{urlencode(params)}"

    def exchange_code(self, code: str) -> OAuthProfile:
        self._require_configured()
        try:
            with httpx.Client(timeout=self._settings.oauth_http_timeout_seconds) as client:
                token_response = client.post(
                    self.token_url,
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": self._settings.github_oauth_client_id,
                        "client_secret": self._settings.github_oauth_client_secret,
                        "code": code,
                        "redirect_uri": self._settings.github_oauth_redirect_uri,
                    },
                )
                token_response.raise_for_status()
                token_payload = token_response.json()
                access_token = token_payload.get("access_token")
                if not isinstance(access_token, str) or not access_token:
                    raise OAuthProviderError("GitHub did not return an access token")

                headers = {
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                }
                user_response = client.get(self.user_url, headers=headers)
                user_response.raise_for_status()
                user_payload = user_response.json()

                emails_response = client.get(self.emails_url, headers=headers)
                emails_response.raise_for_status()
                emails_payload = emails_response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthProviderError("GitHub OAuth request failed") from exc

        return self._profile_from_payloads(user_payload, emails_payload)

    def _require_configured(self) -> None:
        if not self.enabled:
            raise OAuthConfigurationError("GitHub OAuth is not configured")

    @staticmethod
    def _profile_from_payloads(user_payload: object, emails_payload: object) -> OAuthProfile:
        if not isinstance(user_payload, dict):
            raise OAuthProviderError("GitHub user response had an unexpected shape")
        provider_user_id = user_payload.get("id")
        if not isinstance(provider_user_id, int | str):
            raise OAuthProviderError("GitHub user response did not include an id")

        email = _primary_verified_email(emails_payload)
        if not email:
            raise OAuthProviderError("GitHub account does not expose a verified primary email")

        display_name = user_payload.get("name") or user_payload.get("login") or ""
        avatar_url = user_payload.get("avatar_url") or ""
        return OAuthProfile(
            provider=GITHUB_PROVIDER,
            provider_user_id=str(provider_user_id),
            email=email,
            display_name=display_name if isinstance(display_name, str) else "",
            avatar_url=avatar_url if isinstance(avatar_url, str) else "",
        )


def create_oauth_state(settings: Settings, provider: str) -> str:
    payload = {
        "provider": provider,
        "nonce": secrets.token_urlsafe(24),
        "iat": int(time.time()),
    }
    payload_text = _b64url_json(payload)
    signature = _sign(settings.auth_secret_key, payload_text)
    return f"{payload_text}.{signature}"


def verify_oauth_state(settings: Settings, state: str, expected_provider: str) -> None:
    try:
        payload_text, signature = state.split(".", 1)
        expected_signature = _sign(settings.auth_secret_key, payload_text)
        if not hmac.compare_digest(signature, expected_signature):
            raise OAuthStateError("OAuth state signature is invalid")
        payload = json.loads(_b64url_decode(payload_text))
    except (ValueError, json.JSONDecodeError) as exc:
        raise OAuthStateError("OAuth state is invalid") from exc

    if payload.get("provider") != expected_provider:
        raise OAuthStateError("OAuth state provider is invalid")
    issued_at = payload.get("iat")
    if not isinstance(issued_at, int) or issued_at + OAUTH_STATE_TTL_SECONDS < int(time.time()):
        raise OAuthStateError("OAuth state expired")


def _primary_verified_email(payload: object) -> str:
    if not isinstance(payload, list):
        return ""
    for item in payload:
        if not isinstance(item, dict):
            continue
        email = item.get("email")
        if item.get("primary") is True and item.get("verified") is True and isinstance(email, str):
            return email.strip().lower()
    return ""


def _sign(secret: str, value: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def _b64url_json(payload: dict[str, object]) -> str:
    return _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
