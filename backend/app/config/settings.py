from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models.agent import ModelTier


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = ""
    database_url: str = "postgresql+asyncpg://agent_team:agent_team_dev@localhost:5432/agent_team"
    redis_url: str = "redis://localhost:6379"
    chroma_persist_dir: str = "./data/chromadb"
    skills_dir: str = "./data/skills"
    github_token: str = ""
    serper_api_key: str = ""

    claude_model_sonnet: str = "claude-sonnet-4-5"
    claude_model_opus: str = "claude-opus-4-5"
    claude_model_haiku: str = "claude-haiku-4-5-20251001"
    default_agent_model_tier: ModelTier = ModelTier.SONNET
    default_team_lead_model_tier: ModelTier = ModelTier.SONNET
    force_all_agents_model_tier: Optional[ModelTier] = ModelTier.SONNET

    # S3 / MinIO
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_name: str = "agent-artifacts"
    s3_region: str = "us-east-1"

    cors_origins: list[str] = ["http://localhost:3000"]

    data_dir: str = "./data"
    teams_file: str = "./data/teams.json"
    workspaces_dir: str = "./data/workspaces"

    @field_validator("anthropic_api_key")
    @classmethod
    def api_key_must_be_set(cls, value: str) -> str:
        if not value or not value.startswith("sk-"):
            raise ValueError(
                "ANTHROPIC_API_KEY must be set in .env and start with 'sk-'"
            )
        return value

    @property
    def claude_model(self) -> str:
        return self.claude_model_sonnet


@lru_cache
def get_settings() -> Settings:
    return Settings()
