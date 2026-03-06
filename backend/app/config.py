from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = ""

    @field_validator("anthropic_api_key")
    @classmethod
    def api_key_must_be_set(cls, v: str) -> str:
        if not v or not v.startswith("sk-"):
            raise ValueError(
                "ANTHROPIC_API_KEY must be set in .env and start with 'sk-'"
            )
        return v
    redis_url: str = "redis://localhost:6379"
    chroma_persist_dir: str = "./data/chromadb"
    skills_dir: str = "./data/skills"
    github_token: str = ""
    serper_api_key: str = ""

    # Model tiers — Sonnet is the minimum, Opus for high-stakes agents/tasks
    claude_model_sonnet: str = "claude-sonnet-4-5"
    claude_model_opus: str = "claude-opus-4-5"

    # Backward-compat alias used by learning.py and team_builder.py (= sonnet)
    @property
    def claude_model(self) -> str:
        return self.claude_model_sonnet

    cors_origins: list[str] = ["http://localhost:3000"]

    data_dir: str = "./data"
    teams_file: str = "./data/teams.json"
    workspaces_dir: str = "./data/workspaces"


@lru_cache
def get_settings() -> Settings:
    return Settings()
