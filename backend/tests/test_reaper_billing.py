"""Tests for Ticket 4.4 — Reaper and monthly billing reset.

Verify section:
  1. Wave with started_at 15 min ago, status='running' → reaped (status='failed').
  2. Wave with started_at 5 min ago, status='running' → NOT reaped.
  3. Workspace with billing_period_start 35 days ago, spend=$42.50 → reset to $0.
  4. Workspace with billing_period_start 15 days ago → nothing changes.
  5. Both functions are idempotent — running twice produces same result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Sequence
from unittest.mock import MagicMock, patch

import pytest

from app.core.reaper import (
    ORPHAN_THRESHOLD_MINUTES,
    reap_orphaned_waves,
)
from app.core.billing import (
    BILLING_PERIOD_DAYS,
    reset_monthly_budgets,
)


# ---------------------------------------------------------------------------
# Mock ORM objects
# ---------------------------------------------------------------------------


@dataclass
class MockWave:
    """Lightweight stand-in for ExecutionWave ORM model."""

    id: str = "wave-001"
    artifact_id: str = "artifact-001"
    celery_task_id: str | None = "celery-task-001"
    status: str = "running"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.started_at is None:
            self.started_at = datetime.now(timezone.utc) - timedelta(minutes=15)


@dataclass
class MockWorkspace:
    """Lightweight stand-in for Workspace ORM model."""

    id: str = "ws-001"
    monthly_spend_usd: Any = Decimal("42.50")
    billing_period_start: datetime | None = None

    def __post_init__(self) -> None:
        if self.billing_period_start is None:
            self.billing_period_start = datetime.now(timezone.utc) - timedelta(days=35)


# ---------------------------------------------------------------------------
# Mock async session
# ---------------------------------------------------------------------------


class MockAsyncSession:
    """Async session mock that returns pre-configured result sets."""

    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = rows
        self._committed = False

    async def execute(self, stmt: Any) -> Any:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = list(self._rows)
        return mock_result

    async def commit(self) -> None:
        self._committed = True

    async def flush(self) -> None:
        pass

    @property
    def committed(self) -> bool:
        return self._committed


# ===========================================================================
# REAPER TESTS
# ===========================================================================


class TestReapOrphanedWaves:
    """Tests for the reaper: detects and marks orphaned execution waves."""

    @pytest.mark.asyncio
    async def test_reaps_wave_running_15_minutes(self) -> None:
        """A wave started 15 min ago with a dead Celery task is reaped."""
        wave = MockWave(
            id="wave-old",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            celery_task_id="dead-task-123",
        )
        db = MockAsyncSession([wave])

        # No active tasks → dead-task-123 is not alive
        with patch(
            "app.core.reaper._get_active_task_ids", return_value=set()
        ):
            count = await reap_orphaned_waves(db)

        assert count == 1
        assert wave.status == "failed"
        assert wave.error_message == "Worker crashed — execution orphaned"
        assert wave.completed_at is not None
        assert db.committed

    @pytest.mark.asyncio
    async def test_does_not_reap_wave_running_5_minutes(self) -> None:
        """A wave started 5 min ago is under threshold — not reaped."""
        wave = MockWave(
            id="wave-young",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        # The query should not return this wave because started_at < cutoff
        # is False.  We simulate this by returning an empty result set.
        db = MockAsyncSession([])

        with patch(
            "app.core.reaper._get_active_task_ids", return_value=set()
        ):
            count = await reap_orphaned_waves(db)

        assert count == 0
        assert wave.status == "running"  # unchanged
        assert wave.error_message is None
        assert wave.completed_at is None

    @pytest.mark.asyncio
    async def test_skips_wave_with_alive_celery_task(self) -> None:
        """A wave whose Celery task is still active is NOT reaped."""
        wave = MockWave(
            id="wave-alive",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=12),
            celery_task_id="alive-task-456",
        )
        db = MockAsyncSession([wave])

        # alive-task-456 IS in the active set
        with patch(
            "app.core.reaper._get_active_task_ids",
            return_value={"alive-task-456"},
        ):
            count = await reap_orphaned_waves(db)

        assert count == 0
        assert wave.status == "running"  # unchanged
        assert wave.error_message is None

    @pytest.mark.asyncio
    async def test_reaps_wave_with_null_celery_task_id(self) -> None:
        """A wave with no celery_task_id is treated as dead."""
        wave = MockWave(
            id="wave-no-task",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            celery_task_id=None,
        )
        db = MockAsyncSession([wave])

        with patch(
            "app.core.reaper._get_active_task_ids", return_value=set()
        ):
            count = await reap_orphaned_waves(db)

        assert count == 1
        assert wave.status == "failed"

    @pytest.mark.asyncio
    async def test_idempotent_reap(self) -> None:
        """Running the reaper twice on the same wave produces the same result.

        After the first reap, the wave's status is 'failed' so it no longer
        matches the query (status='running').  The second run finds no
        candidates and does nothing.
        """
        wave = MockWave(
            id="wave-idem",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        )
        db1 = MockAsyncSession([wave])

        with patch(
            "app.core.reaper._get_active_task_ids", return_value=set()
        ):
            count1 = await reap_orphaned_waves(db1)

        assert count1 == 1
        assert wave.status == "failed"

        # Second run: wave is now 'failed', so the query returns nothing
        db2 = MockAsyncSession([])

        with patch(
            "app.core.reaper._get_active_task_ids", return_value=set()
        ):
            count2 = await reap_orphaned_waves(db2)

        assert count2 == 0
        # wave still failed from first run
        assert wave.status == "failed"

    @pytest.mark.asyncio
    async def test_no_candidates_returns_zero(self) -> None:
        """When there are no orphaned waves, the reaper returns 0."""
        db = MockAsyncSession([])

        with patch(
            "app.core.reaper._get_active_task_ids", return_value=set()
        ):
            count = await reap_orphaned_waves(db)

        assert count == 0
        assert not db.committed

    @pytest.mark.asyncio
    async def test_multiple_orphaned_waves(self) -> None:
        """Multiple orphaned waves are all reaped in one pass."""
        wave1 = MockWave(
            id="wave-a",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            celery_task_id="dead-1",
        )
        wave2 = MockWave(
            id="wave-b",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=25),
            celery_task_id="dead-2",
        )
        db = MockAsyncSession([wave1, wave2])

        with patch(
            "app.core.reaper._get_active_task_ids", return_value=set()
        ):
            count = await reap_orphaned_waves(db)

        assert count == 2
        assert wave1.status == "failed"
        assert wave2.status == "failed"
        assert db.committed

    @pytest.mark.asyncio
    async def test_revokes_alive_task_past_soft_limit(self) -> None:
        """A wave whose task is alive but past the soft time limit is revoked."""
        wave = MockWave(
            id="wave-stuck",
            # 12 minutes > 10 min threshold, but 12*60=720 > 600 soft limit
            started_at=datetime.now(timezone.utc) - timedelta(minutes=12),
            celery_task_id="stuck-task-789",
        )
        db = MockAsyncSession([wave])

        with (
            patch(
                "app.core.reaper._get_active_task_ids",
                return_value={"stuck-task-789"},
            ),
            patch("app.core.reaper._revoke_task") as mock_revoke,
        ):
            count = await reap_orphaned_waves(db)

        # Not reaped (task is alive), but revoked
        assert count == 0
        assert wave.status == "running"  # unchanged — revoke lets orchestrator handle it
        mock_revoke.assert_called_once_with("stuck-task-789")


# ===========================================================================
# BILLING RESET TESTS
# ===========================================================================


class TestResetMonthlyBudgets:
    """Tests for the monthly billing reset."""

    @pytest.mark.asyncio
    async def test_resets_expired_workspace(self) -> None:
        """Workspace with billing_period_start 35 days ago is reset."""
        ws = MockWorkspace(
            id="ws-expired",
            monthly_spend_usd=Decimal("42.50"),
            billing_period_start=datetime.now(timezone.utc) - timedelta(days=35),
        )
        db = MockAsyncSession([ws])

        count = await reset_monthly_budgets(db)

        assert count == 1
        assert ws.monthly_spend_usd == Decimal("0.00")
        assert ws.billing_period_start is not None
        # billing_period_start should be updated to roughly now
        age = datetime.now(timezone.utc) - ws.billing_period_start
        assert age.total_seconds() < 5  # within 5 seconds of now
        assert db.committed

    @pytest.mark.asyncio
    async def test_does_not_reset_fresh_workspace(self) -> None:
        """Workspace with billing_period_start 15 days ago is NOT reset."""
        ws = MockWorkspace(
            id="ws-fresh",
            monthly_spend_usd=Decimal("12.34"),
            billing_period_start=datetime.now(timezone.utc) - timedelta(days=15),
        )
        # The query should not return this workspace — simulate empty result
        db = MockAsyncSession([])

        count = await reset_monthly_budgets(db)

        assert count == 0
        assert ws.monthly_spend_usd == Decimal("12.34")  # unchanged

    @pytest.mark.asyncio
    async def test_resets_null_billing_period_start(self) -> None:
        """Workspace with NULL billing_period_start is treated as expired."""
        ws = MockWorkspace(
            id="ws-null",
            monthly_spend_usd=Decimal("5.00"),
            billing_period_start=None,
        )

        # Need to override __post_init__ default
        ws.billing_period_start = None
        db = MockAsyncSession([ws])

        count = await reset_monthly_budgets(db)

        assert count == 1
        assert ws.monthly_spend_usd == Decimal("0.00")
        assert ws.billing_period_start is not None

    @pytest.mark.asyncio
    async def test_idempotent_reset(self) -> None:
        """Running the reset twice: second run finds no expired workspaces."""
        ws = MockWorkspace(
            id="ws-idem",
            monthly_spend_usd=Decimal("42.50"),
            billing_period_start=datetime.now(timezone.utc) - timedelta(days=35),
        )
        db1 = MockAsyncSession([ws])

        count1 = await reset_monthly_budgets(db1)

        assert count1 == 1
        assert ws.monthly_spend_usd == Decimal("0.00")
        # billing_period_start is now recent

        # Second run: workspace is no longer expired, query returns nothing
        db2 = MockAsyncSession([])

        count2 = await reset_monthly_budgets(db2)

        assert count2 == 0
        # Still zero from first reset
        assert ws.monthly_spend_usd == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_no_expired_workspaces_returns_zero(self) -> None:
        """When no workspaces need resetting, returns 0 and does not commit."""
        db = MockAsyncSession([])

        count = await reset_monthly_budgets(db)

        assert count == 0
        assert not db.committed

    @pytest.mark.asyncio
    async def test_multiple_workspaces_reset(self) -> None:
        """Multiple expired workspaces are all reset in one pass."""
        ws1 = MockWorkspace(
            id="ws-a",
            monthly_spend_usd=Decimal("10.00"),
            billing_period_start=datetime.now(timezone.utc) - timedelta(days=31),
        )
        ws2 = MockWorkspace(
            id="ws-b",
            monthly_spend_usd=Decimal("99.99"),
            billing_period_start=datetime.now(timezone.utc) - timedelta(days=60),
        )
        db = MockAsyncSession([ws1, ws2])

        count = await reset_monthly_budgets(db)

        assert count == 2
        assert ws1.monthly_spend_usd == Decimal("0.00")
        assert ws2.monthly_spend_usd == Decimal("0.00")
        assert db.committed

    @pytest.mark.asyncio
    async def test_zero_spend_workspace_still_gets_period_updated(self) -> None:
        """Even if spend is already $0, billing_period_start is updated."""
        ws = MockWorkspace(
            id="ws-zero",
            monthly_spend_usd=Decimal("0.00"),
            billing_period_start=datetime.now(timezone.utc) - timedelta(days=35),
        )
        db = MockAsyncSession([ws])

        count = await reset_monthly_budgets(db)

        assert count == 1
        assert ws.monthly_spend_usd == Decimal("0.00")
        # Period start updated even though spend was zero
        age = datetime.now(timezone.utc) - ws.billing_period_start
        assert age.total_seconds() < 5


# ===========================================================================
# CONFIGURATION TESTS
# ===========================================================================


class TestConfigurationConstants:
    """Verify that configuration constants match the TDD spec."""

    def test_orphan_threshold_is_10_minutes(self) -> None:
        assert ORPHAN_THRESHOLD_MINUTES == 10

    def test_billing_period_is_30_days(self) -> None:
        assert BILLING_PERIOD_DAYS == 30
