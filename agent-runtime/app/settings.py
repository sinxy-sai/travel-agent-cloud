from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Travel Agent Runtime"
    app_env: str = "local"
    allowed_origins: str = "http://localhost:5173"
    database_url: str = ""
    message_queue_url: str = ""
    redis_url: str = ""
    redis_key_prefix: str = "travel-agent-cloud"
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "travel-agent-exports"
    minio_secure: bool = False
    rpc_timeout_seconds: float = 5.0
    worker_reconnect_initial_seconds: float = 2.0
    worker_reconnect_max_seconds: float = 30.0
    auth_secret_key: str = "travel-agent-cloud-local-dev-secret"
    auth_token_ttl_seconds: int = 60 * 60 * 24 * 7
    auth_cookie_secure: bool = False
    auth_rate_limit_max_attempts: int = 20
    auth_rate_limit_window_seconds: int = 15 * 60
    email_provider: str = "mock"
    email_from: str = "no-reply@travel-agent-cloud.local"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_ssl: bool = False
    smtp_starttls: bool = True
    public_app_url: str = "http://localhost:5173"
    email_verification_token_ttl_seconds: int = 60 * 60 * 24
    password_reset_token_ttl_seconds: int = 60 * 30
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    github_oauth_redirect_uri: str = ""
    oauth_http_timeout_seconds: float = 10.0
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_temperature: float = 0.4
    llm_max_tokens: int = 1200
    llm_timeout_seconds: float = 30.0
    agent_engine: str = "basic"
    travel_tool_provider: str = "mock"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
