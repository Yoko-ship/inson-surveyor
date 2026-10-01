from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    data_mode: str = "synthetic"
    hosting_country: str = "local"
    database_url: str = "sqlite:///./data/surveyor.db"
    storage_dir: Path = Path("data/uploads")
    public_url: str = "http://localhost:8000"
    cookie_secure: bool = False
    bootstrap_admin_login: str = "admin"
    bootstrap_admin_password: str = ""
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    pdf_font_path: str = ""
    max_upload_bytes: int = 15 * 1024 * 1024
    max_document_pages: int = 50
    session_hours: int = 12

    @model_validator(mode="after")
    def deployment_guard(self):
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
