"""
Celery application and task registration for V2 execution engine.

All task bodies are stubs — implementation comes in later sprints.
See docs/TDD/02_BACKEND_ARCHITECTURE_TDD.md Section 3.2 for task specs.
"""

from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded
from celery.schedules import crontab

from app.config.settings import settings

# ---------------------------------------------------------------------------
# Celery app
# ---------------------------------------------------------------------------

celery_app = Celery(
    "agent_team",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Durability — re-queue tasks if a worker crashes before ack
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Result tracking
    task_track_started=True,
    result_expires=3600,  # 1 hour — long-term tracking is in PostgreSQL
    # Worker — single-concurrency for MVP (AD-3: asyncio.gather inside task)
    worker_concurrency=1,
    # Beat schedule
    beat_schedule={
        "reap-orphaned-waves": {
            "task": "app.core.celery_app.reap_orphaned_waves",
            "schedule": 120.0,  # every 2 minutes
        },
        "reset-monthly-budgets": {
            "task": "app.core.celery_app.reset_monthly_budgets",
            "schedule": crontab(minute=0, hour=0),  # daily at 00:00 UTC
        },
    },
)

# ---------------------------------------------------------------------------
# On-demand tasks
# ---------------------------------------------------------------------------


def _dispose_engine() -> None:
    """Synchronously dispose the async engine connection pool.

    Must be called after every asyncio.run() in a Celery task. The async
    engine is a module-level singleton; after asyncio.run() closes the event
    loop the pool holds asyncpg connections attached to that dead loop.
    Disposing via sync_engine.dispose() clears the pool without requiring an
    event loop, avoiding "Future attached to a different loop" on the next task.

    The MissingGreenlet warning from asyncpg is expected and harmless —
    asyncpg's connection.close() is async-only but the pool teardown runs
    synchronously. The connections are cleaned up by the OS regardless.
    """
    import logging as _logging

    _logging.getLogger("sqlalchemy.pool").setLevel(_logging.CRITICAL)
    from app.core.database import engine as _engine
    try:
        _engine.sync_engine.dispose()
    except Exception:
        pass
    finally:
        _logging.getLogger("sqlalchemy.pool").setLevel(_logging.WARNING)


@celery_app.task(
    name="app.core.celery_app.execute_artifact_dag",
    acks_late=True,
    max_retries=0,
    soft_time_limit=600,
    time_limit=660,
)
def execute_artifact_dag(execution_wave_id: str) -> None:
    """Execute a full DAG for one artifact version.

    Loads the ExecutionWave, runs agents wave-by-wave via asyncio.gather,
    uploads results to S3, and creates an ArtifactVersion row.

    Spec: TDD-02 Section 3.2, TDD-03 Section 13.
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    try:
        from app.agents.orchestrator import execute_dag
        asyncio.run(execute_dag(execution_wave_id))
    except SoftTimeLimitExceeded:
        logger.error(
            "execute_artifact_dag timed out: wave=%s", execution_wave_id
        )
        _mark_wave_failed_sync(execution_wave_id, "Execution timed out (soft limit exceeded)")
        raise
    except Exception:
        logger.exception(
            "execute_artifact_dag failed: wave=%s", execution_wave_id
        )
        raise
    finally:
        _dispose_engine()


@celery_app.task(
    name="app.core.celery_app.process_document_upload",
    max_retries=3,
    retry_backoff=True,
    soft_time_limit=120,
)
def process_document_upload(document_id: str) -> None:
    """Ingest a document: extract text, chunk, embed, store in pgvector.

    Spec: TDD-02 Section 3.2, TDD-03 Section 2.
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    try:
        from app.agents.document_processor import process_document
        asyncio.run(process_document(document_id))
    except SoftTimeLimitExceeded:
        logger.error("process_document_upload timed out: doc=%s", document_id)
        _mark_document_failed_sync(document_id)
        raise
    except Exception:
        logger.exception("process_document_upload failed: doc=%s", document_id)
        raise
    finally:
        _dispose_engine()


@celery_app.task(
    name="app.core.celery_app.execute_agent_learning",
    soft_time_limit=300,
)
def execute_agent_learning(agent_id: str, topic: str | None = None) -> None:
    """Run the initial learning phase for a newly created agent.

    Builds foundational knowledge via web research, stores as agent_skills.
    When `topic` is provided, performs targeted research on that topic instead
    of the full workspace-context onboarding research.

    Spec: TDD-03 Section 11.2.
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    try:
        from app.agents.learning import execute_learning
        asyncio.run(execute_learning(agent_id, topic=topic))
    except SoftTimeLimitExceeded:
        logger.error("execute_agent_learning timed out: agent=%s", agent_id)
        _recover_agent_sync(agent_id)
        raise
    except Exception:
        logger.exception("execute_agent_learning failed: agent=%s", agent_id)
        raise
    finally:
        _dispose_engine()


@celery_app.task(
    name="app.core.celery_app.execute_agent_reflection",
    soft_time_limit=120,
)
def execute_agent_reflection(agent_id: str) -> None:
    """Run post-approval reflection to extract learnings from recent work.

    Acquires FOR UPDATE lock, analyzes recent artifacts + comments,
    inserts new agent_skills, removes obsolete ones, recalculates level.

    Spec: TDD-03 Section 9, TDD-02 Section 6.
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    try:
        from app.agents.reflection import execute_reflection
        asyncio.run(execute_reflection(agent_id))
    except SoftTimeLimitExceeded:
        logger.error("execute_agent_reflection timed out: agent=%s", agent_id)
        _recover_agent_sync(agent_id)
        raise
    except Exception:
        logger.exception("execute_agent_reflection failed: agent=%s", agent_id)
        raise
    finally:
        _dispose_engine()


# ---------------------------------------------------------------------------
# Sync fallback for marking waves failed outside the async event loop
# ---------------------------------------------------------------------------


def _mark_document_failed_sync(document_id: str) -> None:
    """Mark a document as failed using synchronous DB access."""
    import logging
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import Session

    logger = logging.getLogger(__name__)

    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    ).replace(
        "postgresql+asyncpg://", "postgresql://"
    )

    try:
        sync_engine = create_engine(sync_url)
        with Session(sync_engine) as session:
            from app.models.document import Document

            session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(processing_status="failed")
            )
            session.commit()
        sync_engine.dispose()
    except Exception:
        logger.exception(
            "Failed to mark document %s as failed (sync fallback)", document_id,
        )


def _recover_agent_sync(agent_id: str) -> None:
    """Set an agent back to 'ready' using synchronous DB access.

    Used as a last-resort fallback when the async task handler cannot recover
    (e.g. SoftTimeLimitExceeded kills the event loop).
    """
    import logging
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import Session

    logger = logging.getLogger(__name__)

    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    ).replace(
        "postgresql+asyncpg://", "postgresql://"
    )

    try:
        sync_engine = create_engine(sync_url)
        with Session(sync_engine) as session:
            from app.models.agent import Agent

            session.execute(
                update(Agent)
                .where(Agent.id == agent_id)
                .values(status="ready")
            )
            session.commit()
        sync_engine.dispose()
    except Exception:
        logger.exception(
            "Failed to recover agent %s status (sync fallback)", agent_id,
        )


def _mark_wave_failed_sync(execution_wave_id: str, error_message: str) -> None:
    """Mark an execution wave as failed using synchronous DB access.

    Used as a last-resort fallback when the async orchestrator cannot handle
    the error (e.g. SoftTimeLimitExceeded kills the event loop).
    """
    import logging
    from datetime import datetime, timezone

    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import Session

    logger = logging.getLogger(__name__)

    # Build a sync database URL from the async one.
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    ).replace(
        "postgresql+asyncpg://", "postgresql://"
    )

    try:
        sync_engine = create_engine(sync_url)
        with Session(sync_engine) as session:
            from app.models.execution_wave import ExecutionWave

            session.execute(
                update(ExecutionWave)
                .where(ExecutionWave.id == execution_wave_id)
                .values(
                    status="failed",
                    error_message=error_message[:2000],
                    completed_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
        sync_engine.dispose()
    except Exception:
        logger.exception(
            "Failed to mark wave %s as failed (sync fallback)",
            execution_wave_id,
        )


# ---------------------------------------------------------------------------
# Periodic tasks
# ---------------------------------------------------------------------------


@celery_app.task(name="app.core.celery_app.reap_orphaned_waves")
def reap_orphaned_waves() -> None:
    """Detect execution waves stuck in 'running' for >10 min and mark failed.

    Runs every 2 minutes via Celery Beat.
    Spec: TDD-02 Section 3.2 (Reaper).
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    try:
        from app.core.reaper import reap_orphaned_waves as _reap

        async def _run() -> int:
            from app.core.database import async_session_maker

            async with async_session_maker() as db:
                return await _reap(db)

        count = asyncio.run(_run())
        if count:
            logger.info("Reaper task completed: reaped %d wave(s)", count)
    except Exception:
        logger.exception("Reaper task failed")


@celery_app.task(name="app.core.celery_app.reset_monthly_budgets")
def reset_monthly_budgets() -> None:
    """Reset monthly_spend_usd for workspaces past their 30-day billing period.

    Runs daily at 00:00 UTC via Celery Beat.
    Spec: TDD-02 Section 5.4.
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    try:
        from app.core.billing import reset_monthly_budgets as _reset

        async def _run() -> int:
            from app.core.database import async_session_maker

            async with async_session_maker() as db:
                return await _reset(db)

        count = asyncio.run(_run())
        if count:
            logger.info("Billing reset task completed: reset %d workspace(s)", count)
    except Exception:
        logger.exception("Billing reset task failed")
