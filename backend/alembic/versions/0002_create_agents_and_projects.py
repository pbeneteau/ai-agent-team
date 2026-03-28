"""Create agents and projects tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agents ---
    op.create_table(
        "agents",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("specialization", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="learning", nullable=False),
        sa.Column("readiness_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("progression_level", sa.String(20), server_default="apprenti", nullable=False),
        sa.Column("model_tier", sa.String(10), server_default="sonnet", nullable=False),
        sa.Column("tools", sa.dialects.postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("completed_artifacts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_quality_score", sa.Numeric(3, 1), nullable=True),
        sa.Column("last_reflection_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_agents_workspace_id"),
        sa.CheckConstraint(
            "readiness_score >= 0 AND readiness_score <= 100",
            name="ck_agents_readiness_score_range",
        ),
    )
    op.create_index("ix_agents_workspace_id", "agents", ["workspace_id"])
    op.create_index("ix_agents_workspace_status", "agents", ["workspace_id", "status"])
    op.create_index(
        "ix_agents_workspace_archived",
        "agents",
        ["workspace_id"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("brief_draft", sa.Text(), nullable=True),
        sa.Column("brief_published", sa.Text(), nullable=True),
        sa.Column("brief_fingerprint", sa.String(64), nullable=True),
        sa.Column("brief_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_projects_workspace_id"),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_workspace_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_agents_workspace_archived", table_name="agents")
    op.drop_index("ix_agents_workspace_status", table_name="agents")
    op.drop_index("ix_agents_workspace_id", table_name="agents")
    op.drop_table("agents")
