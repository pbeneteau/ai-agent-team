"""Create contextual_comments and document_chunks tables, add deferred FK on execution_waves

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- contextual_comments ---
    op.create_table(
        "contextual_comments",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("artifact_version_id", sa.Text(), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=True),
        sa.Column("highlight_start", sa.Integer(), nullable=True),
        sa.Column("highlight_end", sa.Integer(), nullable=True),
        sa.Column("highlighted_text", sa.Text(), nullable=True),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("source", sa.String(20), server_default="in_app", nullable=False),
        sa.Column("external_comment_id", sa.String(255), nullable=True),
        sa.Column("resolved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("resolved_in_version_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"], ["artifact_versions.id"],
            name="fk_contextual_comments_artifact_version_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_in_version_id"], ["artifact_versions.id"],
            name="fk_contextual_comments_resolved_in_version_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_contextual_comments_version_id",
        "contextual_comments",
        ["artifact_version_id"],
    )
    op.create_index(
        "uq_contextual_comments_external",
        "contextual_comments",
        ["source", "external_comment_id"],
        unique=True,
        postgresql_where=sa.text("external_comment_id IS NOT NULL"),
    )

    # --- document_chunks ---
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name="fk_document_chunks_document_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])

    # Add the deferred FK from execution_waves.trigger_comment_id -> contextual_comments.id
    # (column was created in Migration 0005 without the FK)
    op.create_foreign_key(
        "fk_execution_waves_trigger_comment_id",
        "execution_waves",
        "contextual_comments",
        ["trigger_comment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop deferred FK first
    op.drop_constraint("fk_execution_waves_trigger_comment_id", "execution_waves", type_="foreignkey")

    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("uq_contextual_comments_external", table_name="contextual_comments")
    op.drop_index("ix_contextual_comments_version_id", table_name="contextual_comments")
    op.drop_table("contextual_comments")
