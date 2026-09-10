from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TBR_", env_file=".env", extra="ignore")

    app_name: str = "Team Belote & Re"
    database_url: str = f"sqlite:///{ROOT / 'data' / 'tbr.db'}"
    secret_key: str = secrets.token_urlsafe(48)
    token_ttl_minutes: int = 60 * 12
    #: Compte administrateur cree au premier demarrage si la base est vide.
    admin_numero: int = 1
    admin_nom: str = "Admin"
    admin_identifiant: str = "Admin"
    admin_password: str = "Music7"
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )
    return settings
