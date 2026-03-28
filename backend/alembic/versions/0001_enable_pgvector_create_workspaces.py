"""Enable pgvector extension and create workspaces table

Revision ID: 0001
Revises: None
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension (required for document_chunks.embedding)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain_description", sa.Text(), nullable=True),
        sa.Column("tech_stack", sa.Text(), nullable=True),
        sa.Column("monthly_budget_usd", sa.Numeric(10, 2), server_default="50.00", nullable=False),
        sa.Column("monthly_spend_usd", sa.Numeric(10, 2), server_default="0.00", nullable=False),
        sa.Column("billing_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onboarding_completed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("workspaces")
    op.execute("DROP EXTENSION IF EXISTS vector")
