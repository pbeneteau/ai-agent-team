"""Cost calculation utilities — pricing, budget checks, atomic cost increments.

Ref: TDD-02 Section 5.2–5.3
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.artifact import Artifact
from app.models.execution_wave import ExecutionWave
from app.models.workspace import Workspace

# ---------------------------------------------------------------------------
# Pricing table — per 1K tokens, updated manually when Anthropic changes rates
# ---------------------------------------------------------------------------

PRICING: dict[str, dict[str, Decimal]] = {
    "sonnet": {"input": Decimal("0.003"), "output": Decimal("0.015")},
    "opus": {"input": Decimal("0.015"), "output": Decimal("0.075")},
    "haiku": {"input": Decimal("0.0008"), "output": Decimal("0.004")},
}

# Fallback tier used when an unknown model string is passed. We default to the
# most expensive tier (opus) so that budget checks remain conservative — the
# system never *under-counts* cost due to a missing mapping.
_FALLBACK_TIER = "opus"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BudgetCheckResult:
    """Result of a budget check — immutable value object."""

    allowed: bool
    remaining: Decimal


# ---------------------------------------------------------------------------
# Pure computation
# ---------------------------------------------------------------------------


def compute_call_cost(
    input_tokens: int,
    output_tokens: int,
    model: str,
) -> Decimal:
    """Compute the USD cost of a single LLM call.

    Args:
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens consumed.
        model: Model tier key (e.g. ``"sonnet"``, ``"opus"``, ``"haiku"``).
                If the key is unknown, falls back to the most expensive tier
                (opus) so budgets are never under-counted.

    Returns:
        Cost in USD as a ``Decimal``.
    """
    rate = PRICING.get(model, PRICING[_FALLBACK_TIER])
    return (
        Decimal(input_tokens) * rate["input"]
        + Decimal(output_tokens) * rate["output"]
    ) / Decimal("1000")


# ---------------------------------------------------------------------------
# Budget checks (async — hit the DB)
# ---------------------------------------------------------------------------


async def check_artifact_budget(
    db: AsyncSession,
    artifact_id: str,
    additional_cost: Decimal,
) -> BudgetCheckResult:
    """Check whether *additional_cost* fits within the artifact's budget.

    Compares ``total_cost_usd + additional_cost`` against ``max_budget_usd``.
    """
    result = await db.execute(
        select(Artifact.total_cost_usd, Artifact.max_budget_usd).where(
            Artifact.id == artifact_id
        )
    )
    row = result.one()
    current_cost = Decimal(str(row.total_cost_usd))
    max_budget = Decimal(str(row.max_budget_usd))

    remaining = max_budget - current_cost
    allowed = additional_cost <= remaining

    return BudgetCheckResult(allowed=allowed, remaining=remaining)


async def check_monthly_budget(
    db: AsyncSession,
    workspace_id: str,
    additional_cost: Decimal,
) -> BudgetCheckResult:
    """Check whether *additional_cost* fits within the workspace monthly budget.

    Compares ``monthly_spend_usd + additional_cost`` against
    ``monthly_budget_usd``.
    """
    result = await db.execute(
        select(Workspace.monthly_spend_usd, Workspace.monthly_budget_usd).where(
            Workspace.id == workspace_id
        )
    )
    row = result.one()
    current_spend = Decimal(str(row.monthly_spend_usd))
    monthly_budget = Decimal(str(row.monthly_budget_usd))

    remaining = monthly_budget - current_spend
    allowed = additional_cost <= remaining

    return BudgetCheckResult(allowed=allowed, remaining=remaining)


# ---------------------------------------------------------------------------
# Atomic cost increment
# ---------------------------------------------------------------------------


async def increment_costs(
    db: AsyncSession,
    execution_wave_id: str,
    artifact_id: str,
    workspace_id: str,
    cost: Decimal,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Atomically increment cost counters on wave, artifact, and workspace.

    Uses SQL-level ``column = column + :value`` expressions so that concurrent
    updates do not cause lost-update anomalies — each statement is atomic at the
    row level within the same transaction.

    The caller is responsible for committing the session.
    """
    # 1. Execution wave — increment cost and token counters
    await db.execute(
        update(ExecutionWave)
        .where(ExecutionWave.id == execution_wave_id)
        .values(
            cost_usd=ExecutionWave.cost_usd + cost,
            input_tokens=ExecutionWave.input_tokens + input_tokens,
            output_tokens=ExecutionWave.output_tokens + output_tokens,
        )
    )

    # 2. Artifact — increment total accumulated cost
    await db.execute(
        update(Artifact)
        .where(Artifact.id == artifact_id)
        .values(total_cost_usd=Artifact.total_cost_usd + cost)
    )

    # 3. Workspace — increment monthly spend
    await db.execute(
        update(Workspace)
        .where(Workspace.id == workspace_id)
        .values(monthly_spend_usd=Workspace.monthly_spend_usd + cost)
    )
