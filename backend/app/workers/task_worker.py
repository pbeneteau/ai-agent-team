"""
ARQ-based async task worker for long-running agent tasks.
Run with: arq app.workers.task_worker.WorkerSettings
"""
import logging
from urllib.parse import urlparse

from arq.connections import RedisSettings

from app.config import get_settings
from app.core.orchestrator import get_orchestrator

logger = logging.getLogger(__name__)


async def execute_agent_task(ctx: dict, task_id: str):
    """ARQ job: execute an agent task by ID."""
    orchestrator = get_orchestrator()
    logger.info("Worker executing task: %s", task_id)
    await orchestrator.execute_task(task_id)
    return {"task_id": task_id, "status": "done"}


async def startup(ctx: dict):
    logger.info("Task worker started")


async def shutdown(ctx: dict):
    logger.info("Task worker stopped")


def _build_redis_settings() -> RedisSettings:
    settings = get_settings()
    url = urlparse(settings.redis_url)
    return RedisSettings(
        host=url.hostname or "localhost",
        port=url.port or 6379,
    )


class WorkerSettings:
    functions = [execute_agent_task]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _build_redis_settings()
