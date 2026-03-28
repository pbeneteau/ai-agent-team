"""Create artifacts table and add deferred FK on agent_skills.source_artifact_id

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- artifacts ---
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("artifact_type", sa.String(10), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(15), server_default="drafting", nullable=False),
        sa.Column("max_budget_usd", sa.Numeric(10, 2), server_default="5.00", nullable=False),
        sa.Column("total_cost_usd", sa.Numeric(10, 2), server_default="0.00", nullable=False),
        sa.Column("current_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("git_repo_url", sa.String(1024), nullable=True),
        sa.Column("git_base_branch", sa.String(255), nullable=True),
        sa.Column("git_feature_branch", sa.String(255), nullable=True),
        sa.Column("git_pr_url", sa.String(1024), nullable=True),
        sa.Column("git_pr_number", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_artifacts_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])
    op.create_index("ix_artifacts_project_status", "artifacts", ["project_id", "status"])
    op.create_index(
        "ix_artifacts_git_pr",
        "artifacts",
        ["git_pr_url"],
        postgresql_where=sa.text("git_pr_url IS NOT NULL"),
    )

    # Add the deferred FK from agent_skills.source_artifact_id -> artifacts.id
    # (column was created in Migration 0003 without the FK)
    op.create_foreign_key(
        "fk_agent_skills_source_artifact_id",
        "agent_skills",
        "artifacts",
        ["source_artifact_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop deferred FK first
    op.drop_constraint("fk_agent_skills_source_artifact_id", "agent_skills", type_="foreignkey")

    op.drop_index("ix_artifacts_git_pr", table_name="artifacts")
    op.drop_index("ix_artifacts_project_status", table_name="artifacts")
    op.drop_index("ix_artifacts_project_id", table_name="artifacts")
    op.drop_table("artifacts")
