"""Add code-factory fields to projects: primary_language, framework, package_manager, git_repo_url.

Revision ID: 0011
Revises: 0010
"""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("primary_language", sa.String(50), nullable=True))
    op.add_column("projects", sa.Column("framework", sa.String(100), nullable=True))
    op.add_column("projects", sa.Column("package_manager", sa.String(50), nullable=True))
    op.add_column("projects", sa.Column("git_repo_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "git_repo_url")
    op.drop_column("projects", "package_manager")
    op.drop_column("projects", "framework")
    op.drop_column("projects", "primary_language")
