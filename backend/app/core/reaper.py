"""Reaper — detects orphaned execution waves and marks them as failed.

Ref: TDD-02 Section 3.2 (reap_orphaned_waves periodic task spec).

An execution wave becomes "orphaned" when its Celery worker crashes or is
killed after setting ``status = 'running'`` but before completing.  Without
the reaper, such waves stay in ``running`` forever — the artifact remains
stuck in ``drafting`` and the user sees a perpetual spinner.

The reaper runs every 2 minutes via Celery Beat.  It:

1. Queries for waves with ``status = 'running'`` and ``started_at`` older
   than the orphan threshold (10 minutes).
2. For each candidate, checks whether the Celery task is still alive.
3. If the task is dead (or the worker is unreachable): marks the wave
   ``failed`` with an explanatory error message.
4. If the task is alive but past the soft time limit: revokes it — Celery
   will raise ``SoftTimeLimitExceeded`` inside the worker, which the
   orchestrator's error handler catches.

The parent artifact is left in ``drafting`` — the user decides whether to
retry or cancel.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_wave import ExecutionWave

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ORPHAN_THRESHOLD_MINUTES: int = 10
"""Waves running longer than this are candidates for reaping."""

SOFT_TIME_LIMIT_SECONDS: int = 600
"""Celery soft_time_limit for execute_artifact_dag (must match celery_app.py)."""


# ---------------------------------------------------------------------------
# Celery task liveness check
# ---------------------------------------------------------------------------


def _get_active_task_ids() -> set[str]:
    """Return the set of currently active Celery task IDs across all workers.

    Uses ``celery_app.control.inspect().active()`` which pings every live
    worker and collects their active task lists.

    If no workers respond (all down, network partition, etc.), returns an
    empty set — meaning *every* running wave is treated as orphaned.  This
    is the correct behavior: if no workers are alive, no running task can
    possibly make progress.
    """
    try:
        from app.core.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=2.0)
        active: dict[str, list[dict[str, Any]]] | None = inspector.active()

        if active is None:
            # No workers responded.
            logger.warning(
                "Reaper: no Celery workers responded to inspect — "
                "treating all running waves as orphaned"
            )
            return set()

        task_ids: set[str] = set()
        for worker_tasks in active.values():
            for task_info in worker_tasks:
                tid = task_info.get("id")
                if tid:
                    task_ids.add(tid)
        return task_ids

    except Exception:
        logger.exception(
            "Reaper: failed to inspect Celery workers — "
            "treating all running waves as orphaned"
        )
        return set()


def _revoke_task(celery_task_id: str) -> None:
    """Revoke a Celery task by ID (sends SIGTERM via soft termination).

    The worker will raise ``SoftTimeLimitExceeded`` inside the task,
    which the orchestrator catches and handles gracefully.
    """
    try:
        from app.core.celery_app import celery_app

        celery_app.control.revoke(celery_task_id, terminate=True, signal="SIGTERM")
        logger.info("Reaper: revoked task %s", celery_task_id)
    except Exception:
        logger.exception("Reaper: failed to revoke task %s", celery_task_id)


# ---------------------------------------------------------------------------
# Main reaper logic
# ---------------------------------------------------------------------------


async def reap_orphaned_waves(db: AsyncSession) -> int:
    """Find and reap orphaned execution waves.

    An orphaned wave is one with:
    - ``status = 'running'``
    - ``started_at`` older than ``ORPHAN_THRESHOLD_MINUTES`` minutes ago

    For each orphaned wave:
    - If its Celery task is dead → mark ``failed``.
    - If its Celery task is alive but past the soft time limit → revoke it
      (the orchestrator's error handler will mark it failed).

    Args:
        db: Async SQLAlchemy session.  The caller is responsible for
            committing after this function returns.

    Returns:
        Number of waves reaped (marked as failed).
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=ORPHAN_THRESHOLD_MINUTES)

    # 1. Find candidate orphaned waves
    result = await db.execute(
        select(ExecutionWave)
        .where(ExecutionWave.status == "running")
        .where(ExecutionWave.started_at < cutoff)
    )
    candidates: Sequence[ExecutionWave] = result.scalars().all()

    if not candidates:
        return 0

    logger.info(
        "Reaper: found %d candidate orphaned wave(s)", len(candidates)
    )

    # 2. Get active Celery task IDs (one network call, not per-wave)
    active_task_ids: set[str] = _get_active_task_ids()

    # 3. Process each candidate
    reaped_count: int = 0

    for wave in candidates:
        wave_age = now - wave.started_at  # type: ignore[operator]
        age_minutes = wave_age.total_seconds() / 60

        celery_task_id: str | None = wave.celery_task_id

        # Check if the Celery task is still alive
        task_alive = (
            celery_task_id is not None
            and celery_task_id in active_task_ids
        )

        if task_alive:
            # Task is alive but has exceeded the orphan threshold.
            # If past the soft time limit, revoke it — the orchestrator
            # will handle the SoftTimeLimitExceeded and mark it failed.
            if wave_age.total_seconds() > SOFT_TIME_LIMIT_SECONDS:
                logger.warning(
                    "Reaper: wave %s is alive but past soft time limit "
                    "(%.1f min) — revoking task %s",
                    wave.id, age_minutes, celery_task_id,
                )
                _revoke_task(celery_task_id)  # type: ignore[arg-type]
            else:
                # Alive and within soft limit — leave it alone.
                logger.debug(
                    "Reaper: wave %s is still alive (%.1f min) — skipping",
                    wave.id, age_minutes,
                )
            continue

        # Task is dead — mark wave as failed
        logger.warning(
            "Reaper: marking wave %s as failed (orphaned %.1f min, "
            "artifact=%s, celery_task=%s)",
            wave.id, age_minutes, wave.artifact_id, celery_task_id,
        )

        wave.status = "failed"
        wave.error_message = "Worker crashed — execution orphaned"
        wave.completed_at = now

        reaped_count += 1

    if reaped_count > 0:
        await db.commit()
        logger.info("Reaper: reaped %d orphaned wave(s)", reaped_count)

    return reaped_count
