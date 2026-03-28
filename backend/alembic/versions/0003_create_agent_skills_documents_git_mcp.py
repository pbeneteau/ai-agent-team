"""Create agent_skills, documents, git_provider_connections, mcp_connections tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agent_skills ---
    # NOTE: source_artifact_id column is created here as nullable TEXT,
    # but the FK constraint to artifacts.id is deferred to Migration 0004
    # because the artifacts table does not exist yet.
    op.create_table(
        "agent_skills",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("source_artifact_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"],
            name="fk_agent_skills_agent_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_agent_skills_agent_id", "agent_skills", ["agent_id"])
    op.create_index("ix_agent_skills_agent_category", "agent_skills", ["agent_id", "category"])

    # --- documents ---
    op.create_table(
        "documents",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("s3_path", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processing_status", sa.String(15), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_documents_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_documents_project_id", "documents", ["project_id"])

    # --- git_provider_connections ---
    op.create_table(
        "git_provider_connections",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(10), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("repositories", sa.dialects.postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("status", sa.String(10), server_default="active", nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name="fk_git_connections_workspace_id",
        ),
    )
    op.create_index("ix_git_connections_workspace_id", "git_provider_connections", ["workspace_id"])

    # --- mcp_connections ---
    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("server_url", sa.String(1024), nullable=False),
        sa.Column("auth_type", sa.String(20), server_default="api_key", nullable=False),
        sa.Column("auth_config_encrypted", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("discovered_tools", sa.dialects.postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("status", sa.String(15), server_default="active", nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name="fk_mcp_connections_workspace_id",
        ),
    )
    op.create_index("ix_mcp_connections_workspace_id", "mcp_connections", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_mcp_connections_workspace_id", table_name="mcp_connections")
    op.drop_table("mcp_connections")

    op.drop_index("ix_git_connections_workspace_id", table_name="git_provider_connections")
    op.drop_table("git_provider_connections")

    op.drop_index("ix_documents_project_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_agent_skills_agent_category", table_name="agent_skills")
    op.drop_index("ix_agent_skills_agent_id", table_name="agent_skills")
    op.drop_table("agent_skills")
