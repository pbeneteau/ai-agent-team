from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL (asyncpg)
    DATABASE_URL: str = "postgresql+asyncpg://agent_team:agent_team_dev@localhost:5432/agent_team"

    # Redis (Celery broker + result backend)
    REDIS_URL: str = "redis://localhost:6379"

    # MinIO / S3
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "agent-artifacts"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Model tiers
    MODEL_SONNET: str = "claude-sonnet-4-20250514"
    MODEL_HAIKU: str = "claude-haiku-4-5-20251001"
    MODEL_OPUS: str = "claude-opus-4-20250514"

    # Optional integrations
    SERPER_API_KEY: Optional[str] = None
    VOYAGE_API_KEY: Optional[str] = None

    # Encryption key for PATs and auth configs (Fernet)
    ENCRYPTION_KEY: str = "dev-secret-change-in-production"

    # Webhook base URL (used when auto-configuring webhooks on repos)
    WEBHOOK_BASE_URL: str = "http://localhost:8000"

    # CORS
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3000"])


settings = Settings()
