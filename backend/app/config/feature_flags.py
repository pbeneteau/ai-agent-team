from app.config.settings import Settings


def has_web_search(settings: Settings) -> bool:
    return bool(settings.serper_api_key.strip())


def has_github_access(settings: Settings) -> bool:
    return bool(settings.github_token.strip())


def has_model_override(settings: Settings) -> bool:
    return settings.force_all_agents_model_tier is not None
