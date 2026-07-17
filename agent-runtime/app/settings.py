from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Travel Agent Runtime"
    app_env: str = "local"
    allowed_origins: str = "http://localhost:5173"
    rpc_timeout_seconds: float = 5.0
    auth_secret_key: str = "travel-agent-cloud-local-dev-secret"
    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_temperature: float = 0.4
    llm_max_tokens: int = 1200
    llm_timeout_seconds: float = 30.0
    agent_engine: str = "basic"
    travel_tool_provider: str = "mock"
    fastmcp_base_url: str = ""
    fastmcp_auth_token: str = ""
    fastmcp_timeout_seconds: float = 8.0
    fastmcp_attractions_tool: str = "travel.search_attractions"
    fastmcp_hotel_tool: str = "travel.search_hotel"
    fastmcp_meals_tool: str = "travel.search_meals"
    fastmcp_routes_tool: str = "travel.plan_routes"
    fastmcp_weather_tool: str = "travel.get_weather"
    fastmcp_budget_tool: str = "travel.estimate_budget"
    internal_service_token: str = ""
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
