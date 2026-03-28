import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base
from app.models.enums import GitConnectionStatus, GitProvider

if TYPE_CHECKING:
    from app.models.workspace import Workspace


class GitProviderConnection(Base):
    __tablename__ = "git_provider_connections"
    __table_args__ = (
        Index("ix_git_connections_workspace_id", "workspace_id"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("workspaces.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(10), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    repositories: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    webhook_secret: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(10), default=GitConnectionStatus.ACTIVE.value, server_default=GitConnectionStatus.ACTIVE.value
    )
    last_verified_at: Mapped["datetime.datetime | None"] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(back_populates="git_provider_connections")

    def __repr__(self) -> str:
        return f"<GitProviderConnection id={self.id!r} provider={self.provider!r} name={self.display_name!r}>"
