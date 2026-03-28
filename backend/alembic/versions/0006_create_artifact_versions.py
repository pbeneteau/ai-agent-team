"""Create artifact_versions table

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "artifact_versions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("s3_prefix", sa.String(1024), nullable=False),
        sa.Column("file_manifest", sa.dialects.postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("token_cost_usd", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("assumptions", sa.dialects.postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("sources", sa.dialects.postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("execution_wave_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["artifacts.id"],
            name="fk_artifact_versions_artifact_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["execution_wave_id"], ["execution_waves.id"],
            name="fk_artifact_versions_execution_wave_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "artifact_id", "version_number",
            name="uq_artifact_versions_artifact_version",
        ),
    )
    op.create_index("ix_artifact_versions_artifact_id", "artifact_versions", ["artifact_id"])


def downgrade() -> None:
    op.drop_index("ix_artifact_versions_artifact_id", table_name="artifact_versions")
    op.drop_table("artifact_versions")
