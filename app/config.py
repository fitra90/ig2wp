"""
Application configuration loaded from environment variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Centralised settings – values are read from `.env` automatically."""

    # Instagram – target profile to scrape
    ig_username: str = ""

    # Instagram – optional login for session-based access (reduces blocking)
    ig_session_user: str = ""
    ig_session_pass: str = ""

    # WordPress REST API
    wp_url: str = ""
    wp_username: str = ""
    wp_app_password: str = ""

    # Scheduler – default 1440 min = 24 hours (1x per day)
    sync_interval_minutes: int = 1440

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
