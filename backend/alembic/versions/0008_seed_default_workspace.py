"""Seed default workspace for single-tenant MVP

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Hardcoded default workspace UUID (referenced by AD-1 get_workspace_id() dependency)
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO workspaces (id, name, onboarding_completed, monthly_budget_usd, monthly_spend_usd, created_at, updated_at)
        VALUES (
            '{DEFAULT_WORKSPACE_ID}',
            'Default Workspace',
            false,
            50.00,
            0.00,
            NOW(),
            NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM workspaces WHERE id = '{DEFAULT_WORKSPACE_ID}'"
    )
