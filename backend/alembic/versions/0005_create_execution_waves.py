"""Create execution_waves table

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: trigger_comment_id column is created here as nullable TEXT,
    # but the FK constraint to contextual_comments.id is deferred to Migration 0007
    # because the contextual_comments table does not exist yet.
    op.create_table(
        "execution_waves",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("trigger_comment_id", sa.Text(), nullable=True),
        sa.Column("dag_plan", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("assembled_team", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(15), server_default="queued", nullable=False),
        sa.Column("current_step", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_steps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("step_labels", sa.dialects.postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["artifacts.id"],
            name="fk_execution_waves_artifact_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_execution_waves_artifact_id", "execution_waves", ["artifact_id"])
    op.create_index(
        "ix_execution_waves_status",
        "execution_waves",
        ["status"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("ix_execution_waves_status", table_name="execution_waves")
    op.drop_index("ix_execution_waves_artifact_id", table_name="execution_waves")
    op.drop_table("execution_waves")
