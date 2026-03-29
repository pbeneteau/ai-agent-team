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

    # -----------------------------------------------------------------------
    # Agent tuning parameters (Ticket 17.6, AD-30)
    #
    # All values are current defaults from TDD-03.  Override via env vars
    # after analyzing telemetry data.  See scripts/analyze_telemetry.py.
    # -----------------------------------------------------------------------

    # Agent execution loop
    AGENT_MAX_TOOL_ITERATIONS: int = 15
    AGENT_DEFAULT_MAX_TOKENS: int = 8192

    # Memory budget (tokens)
    AGENT_MEMORY_BUDGET_TOTAL: int = 8_000
    AGENT_MEMORY_BUDGET_SKILLS: int = 6_000
    AGENT_MEMORY_BUDGET_LEARNINGS: int = 2_000

    # Upstream context
    AGENT_UPSTREAM_TOKEN_CAP: int = 15_000

    # Orchestrator
    AGENT_SLOT_MAX_RETRIES: int = 3
    AGENT_SLOT_RETRY_BACKOFF_BASE: int = 2
    AGENT_MAX_VALIDATION_REPLANS: int = 1

    # Context summarization
    AGENT_CONTEXT_SUMMARIZATION_THRESHOLD: int = 60_000
    AGENT_SUMMARIZATION_CHECK_INTERVAL: int = 3

    # Code execution sandbox
    AGENT_CODE_EXEC_TIMEOUT: int = 30

    # CORS
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3005"])


settings = Settings()
