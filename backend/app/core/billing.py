"""Billing — monthly budget reset for workspaces.

Ref: TDD-02 Section 5.4 (monthly budget reset specification).

A Celery Beat periodic task runs daily at 00:00 UTC.  For each workspace
whose ``billing_period_start`` is older than 30 days, it:

1. Zeros ``monthly_spend_usd``.
2. Sets ``billing_period_start`` to ``NOW()``.

This is the billing clock for the three-tier cost enforcement system
(TDD-02 Section 5).  Without it, workspaces that hit their monthly cap
would be permanently locked out.

The reset is idempotent: running it twice on the same workspace within
the same billing period produces the same result (the second run finds
no expired workspaces).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BILLING_PERIOD_DAYS: int = 30
"""Length of a billing period in days."""


# ---------------------------------------------------------------------------
# Main billing reset logic
# ---------------------------------------------------------------------------


async def reset_monthly_budgets(db: AsyncSession) -> int:
    """Reset monthly spend for workspaces whose billing period has expired.

    A workspace's billing period is expired when ``billing_period_start``
    is older than ``BILLING_PERIOD_DAYS`` days ago.  Workspaces with a
    ``NULL`` ``billing_period_start`` are also treated as expired (they
    have never been initialized — set them up now).

    For each expired workspace:
    - Set ``monthly_spend_usd = 0``.
    - Set ``billing_period_start = NOW()``.

    Each workspace is handled individually so that a DB error on one
    does not block others.

    Args:
        db: Async SQLAlchemy session.

    Returns:
        Number of workspaces reset.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=BILLING_PERIOD_DAYS)

    # Find workspaces with expired billing period or NULL period start
    result = await db.execute(
        select(Workspace).where(
            (Workspace.billing_period_start < cutoff)
            | (Workspace.billing_period_start.is_(None))
        )
    )
    candidates: Sequence[Workspace] = result.scalars().all()

    if not candidates:
        logger.debug("Billing reset: no workspaces need resetting")
        return 0

    logger.info(
        "Billing reset: found %d workspace(s) with expired billing period",
        len(candidates),
    )

    reset_count: int = 0

    for workspace in candidates:
        previous_spend = workspace.monthly_spend_usd
        previous_period_start = workspace.billing_period_start

        try:
            workspace.monthly_spend_usd = Decimal("0.00")
            workspace.billing_period_start = now

            logger.info(
                "Billing reset: workspace %s — "
                "previous_spend=$%.2f, previous_period_start=%s",
                workspace.id,
                float(previous_spend) if previous_spend else 0.0,
                previous_period_start,
            )
            reset_count += 1

        except Exception:
            logger.exception(
                "Billing reset: failed to reset workspace %s — skipping",
                workspace.id,
            )
            continue

    if reset_count > 0:
        await db.commit()
        logger.info("Billing reset: reset %d workspace(s)", reset_count)

    return reset_count
