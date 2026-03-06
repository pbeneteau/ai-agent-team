from crewai import Agent, LLM
from typing import Optional
import logging

from app.config import get_settings
from app.models.agent import AgentConfig, ModelTier

logger = logging.getLogger(__name__)


def build_llm(model_tier: ModelTier = ModelTier.SONNET, max_tokens: int = 8192) -> LLM:
    settings = get_settings()
    model = (
        settings.claude_model_opus
        if model_tier == ModelTier.OPUS
        else settings.claude_model_sonnet
    )
    logger.debug("Building LLM: %s (tier=%s)", model, model_tier.value)
    return LLM(
        model=f"anthropic/{model}",
        api_key=settings.anthropic_api_key,
        temperature=0.7,
        max_tokens=max_tokens,
    )


def build_crewai_agent(
    config: AgentConfig,
    tools: Optional[list] = None,
    backstory_override: Optional[str] = None,
) -> Agent:
    settings = get_settings()
    model = (
        settings.claude_model_opus
        if config.model_tier == ModelTier.OPUS
        else settings.claude_model_sonnet
    )
    llm = LLM(
        model=f"anthropic/{model}",
        api_key=settings.anthropic_api_key,
        temperature=0.7,
        max_tokens=config.max_tokens,
    )
    logger.info(
        "Spawning agent '%s' (%s) — model=%s, max_iter=%d, max_tokens=%d",
        config.name, config.title, config.model_tier.value, config.max_iter, config.max_tokens,
    )
    return Agent(
        role=config.title,
        goal=config.goal,
        backstory=backstory_override if backstory_override is not None else config.backstory,
        llm=llm,
        tools=tools or [],
        verbose=True,
        allow_delegation=config.role.value in ("associate", "team_lead"),
        max_iter=config.max_iter,
        max_tokens=config.max_tokens,
    )
