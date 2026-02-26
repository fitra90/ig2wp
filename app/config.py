"""
Application configuration loaded from environment variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Centralised settings – values are read from `.env` automatically."""

    # Instagram Graph API
    ig_access_token: str = ""
    ig_user_id: str = ""

    # WordPress REST API
    wp_url: str = ""
    wp_username: str = ""
    wp_app_password: str = ""

    # Scheduler
    sync_interval_minutes: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
