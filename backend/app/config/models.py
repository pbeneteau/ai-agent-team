from app.config.settings import Settings
from app.models.agent import ModelTier


def get_default_model_tier(settings: Settings, *, is_lead: bool) -> ModelTier:
    forced = settings.force_all_agents_model_tier
    if forced is not None:
        return forced
    return (
        settings.default_team_lead_model_tier
        if is_lead
        else settings.default_agent_model_tier
    )
