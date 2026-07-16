import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def allowed_origins_from_env(
    env_name: str = "ALLOWED_ORIGINS",
    default: str = "http://localhost:5173",
) -> list[str]:
    origins = [origin.strip() for origin in os.getenv(env_name, default).split(",") if origin.strip()]
    return origins or [default]


def add_cors(app: FastAPI, *, allowed_origins: list[str]) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins if allowed_origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
