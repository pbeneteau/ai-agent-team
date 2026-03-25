"""
Agent model helpers — native Anthropic, no CrewAI.
"""
import logging

from app.config import get_settings
from app.models.agent import AgentConfig, ModelTier

logger = logging.getLogger(__name__)


def build_agent_model_name(cfg: AgentConfig) -> str:
    """Return the Anthropic model name for the given agent, based on its model_tier."""
    settings = get_settings()
    model = (
        settings.claude_model_opus
        if cfg.model_tier == ModelTier.OPUS
        else settings.claude_model_sonnet
    )
    logger.debug(
        "Resolved model for agent '%s' (%s): %s (tier=%s)",
        cfg.name, cfg.title, model, cfg.model_tier.value,
    )
    return model
