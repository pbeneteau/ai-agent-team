"""Add role column to agents table

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "role",
            sa.String(10),
            server_default="worker",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "role")
