from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    data_mode: str = "synthetic"
    hosting_country: str = "local"
    database_url: str = "sqlite:///./data/surveyor.db"
    storage_dir: Path = Path("data/uploads")
    public_url: str = "http://localhost:8010"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    bootstrap_admin_login: str = "admin"
    bootstrap_admin_password: str = ""
    telegram_bot_token: str = ""
    telegram_expected_bot_id: str = ""
    telegram_webhook_secret: str = ""
    pdf_font_path: str = ""
    max_upload_bytes: int = 15 * 1024 * 1024
    max_document_pages: int = 50
    session_hours: int = 12
    backup_dir: Path = Path("data/backups")
    backup_enabled: bool = True
    backup_retention_days: int = 14
    codex_local_pilot: bool = False
    codex_cli_path: str = ""
    codex_telegram_enabled: bool = False
    codex_telegram_owner_id: str = ""

    @model_validator(mode="after")
    def deployment_guard(self):
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("SameSite=None requires COOKIE_SECURE=true")
        if self.data_mode not in {"synthetic", "real"}:
            raise ValueError("DATA_MODE must be synthetic or real")
        if self.data_mode == "real" and self.hosting_country.upper() != "UZ":
            raise ValueError("Real data requires hosting in Uzbekistan (HOSTING_COUNTRY=UZ)")
        if self.app_env == "production" and (
            not self.cookie_secure or not self.public_url.startswith("https://")
        ):
            raise ValueError("Production requires HTTPS and COOKIE_SECURE=true")
        return self


settings = Settings()
