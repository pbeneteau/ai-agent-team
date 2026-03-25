"""Celery application — durable execution for the Artifact-First pipeline.

Workers are started via:
    celery -A app.core.celery_app worker --loglevel=info
"""

import asyncio
import logging
import traceback

from celery import Celery
from anthropic import AsyncAnthropic
from sqlalchemy import select

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

celery = Celery(
    "agent_team",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


# ---------------------------------------------------------------------------
# Auto-Assume prompt suffix — injected into every agent system prompt so the
# agent never pauses for human input.
# ---------------------------------------------------------------------------
AUTO_ASSUME_SUFFIX = """

CRITICAL RULE — AUTO-ASSUME:
If you encounter missing information, ambiguity, or a situation where you would
normally ask the user for clarification, you MUST NOT stop or ask. Instead:
1. Make the safest reasonable assumption.
2. Clearly document the assumption inline in the output using this exact format:
   [⚠️ ASSUMPTION MADE: <what you assumed and why>]
3. Continue working and finish the deliverable.
You are autonomous. Never pause for human input."""


async def _generate_artifact_async(artifact_id: str) -> dict:
    """Core async logic for artifact generation — called inside the Celery task."""
    from app.core.database import async_session
    from app.core.s3_workspace import S3WorkspaceManager
    from app.core.usage_tracker import get_usage_tracker, _cost_usd
    from app.models.domain import Artifact, ArtifactVersion, ArtifactStatus

    # 1. Load artifact from Postgres
    async with async_session() as session:
        result = await session.execute(select(Artifact).where(Artifact.id == artifact_id))
        artifact = result.scalar_one_or_none()
        if not artifact:
            raise ValueError(f"Artifact {artifact_id} not found")

        artifact_title = artifact.title
        artifact_goal = artifact.goal or ""
        project_id = artifact.project_id

        # Determine next version number
        from sqlalchemy import func
        max_v = await session.execute(
            select(func.coalesce(func.max(ArtifactVersion.version_number), 0))
            .where(ArtifactVersion.artifact_id == artifact_id)
        )
        next_version = max_v.scalar() + 1

    # 2. Build the prompt
    system_prompt = (
        "You are a specialist agent in an autonomous AI workforce. "
        "Produce a complete, high-quality deliverable based on the brief below. "
        "Output the deliverable content directly — no preamble, no meta-commentary."
        + AUTO_ASSUME_SUFFIX
    )

    user_message = f"# Brief\n\n**Title:** {artifact_title}\n\n**Goal:** {artifact_goal}"

    # 3. Run the LLM agent
    model = settings.claude_model_sonnet
    if settings.force_all_agents_model_tier:
        tier = settings.force_all_agents_model_tier.value
        if tier == "opus":
            model = settings.claude_model_opus
        elif tier == "haiku":
            model = settings.claude_model_haiku

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    usage_tracker = get_usage_tracker()

    result_text = ""
    input_tokens = 0
    output_tokens = 0

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        result_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        usage_tracker.log(model, input_tokens, output_tokens)
    except Exception as exc:
        # Auto-Assume: do not fail — produce a partial artifact with the error documented
        logger.warning("Agent execution failed for artifact %s: %s", artifact_id, exc)
        result_text = (
            f"# {artifact_title}\n\n"
            f"[⚠️ ASSUMPTION MADE: The agent encountered an error during generation "
            f"({type(exc).__name__}: {exc}). This is a partial draft that needs human review.]\n\n"
            f"Goal: {artifact_goal}\n\n"
            f"*The agent was unable to complete this deliverable. "
            f"Please iterate with a contextual comment to retry.*"
        )

    token_cost = _cost_usd(model, input_tokens, output_tokens)

    # 4. Upload to S3
    s3 = S3WorkspaceManager()
    s3_key = await s3.upload_artifact_version(result_text, artifact_id, next_version)

    # 5. Create ArtifactVersion in Postgres and update Artifact status
    async with async_session() as session:
        version = ArtifactVersion(
            artifact_id=artifact_id,
            version_number=next_version,
            s3_file_path=s3_key,
            token_cost=token_cost,
        )
        session.add(version)

        # Update artifact status to IN_REVIEW
        result = await session.execute(select(Artifact).where(Artifact.id == artifact_id))
        artifact = result.scalar_one()
        artifact.status = ArtifactStatus.IN_REVIEW

        await session.commit()

    logger.info(
        "Artifact %s v%d generated — %d input / %d output tokens ($%.4f)",
        artifact_id, next_version, input_tokens, output_tokens, token_cost,
    )

    return {
        "artifact_id": artifact_id,
        "version": next_version,
        "s3_key": s3_key,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": token_cost,
    }


@celery.task(name="generate_artifact", bind=True, max_retries=2, default_retry_delay=10)
def generate_artifact(self, artifact_id: str) -> dict:
    """Celery task: generate an artifact version from a brief.

    Takes an artifact_id, runs the LLM pipeline, uploads the result to S3,
    creates an ArtifactVersion row, and flips the Artifact to IN_REVIEW.
    """
    try:
        return asyncio.run(_generate_artifact_async(artifact_id))
    except Exception as exc:
        logger.exception("generate_artifact failed for %s", artifact_id)
        raise self.retry(exc=exc)
