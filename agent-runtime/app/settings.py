from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Travel Agent Runtime"
    app_env: str = "local"
    allowed_origins: str = "http://localhost:5173"
    database_url: str = ""
    message_queue_url: str = ""
    rpc_timeout_seconds: float = 5.0
    worker_reconnect_initial_seconds: float = 2.0
    worker_reconnect_max_seconds: float = 30.0
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_temperature: float = 0.4
    llm_max_tokens: int = 1200
    llm_timeout_seconds: float = 30.0
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
