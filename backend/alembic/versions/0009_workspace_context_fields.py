"""Add context fields to workspaces and workspace_id to documents

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new context columns to workspaces
    op.add_column("workspaces", sa.Column("product_description", sa.Text(), nullable=True))
    op.add_column("workspaces", sa.Column("company_stage", sa.String(50), nullable=True))
    op.add_column("workspaces", sa.Column("target_audience", sa.Text(), nullable=True))
    op.add_column("workspaces", sa.Column("main_goals", sa.Text(), nullable=True))
    op.add_column("workspaces", sa.Column("existing_team", sa.Text(), nullable=True))

    # Make documents.project_id nullable and add workspace_id FK
    op.alter_column("documents", "project_id", nullable=True)
    op.add_column(
        "documents",
        sa.Column(
            "workspace_id",
            sa.Text(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_workspace_id", table_name="documents")
    op.drop_column("documents", "workspace_id")
    op.alter_column("documents", "project_id", nullable=False)

    op.drop_column("workspaces", "existing_team")
    op.drop_column("workspaces", "main_goals")
    op.drop_column("workspaces", "target_audience")
    op.drop_column("workspaces", "company_stage")
    op.drop_column("workspaces", "product_description")
