import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base
from app.models.enums import McpAuthType, McpConnectionStatus

if TYPE_CHECKING:
    from app.models.workspace import Workspace


class McpConnection(Base):
    __tablename__ = "mcp_connections"
    __table_args__ = (
        Index("ix_mcp_connections_workspace_id", "workspace_id"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("workspaces.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    server_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    auth_type: Mapped[str] = mapped_column(
        String(20), default=McpAuthType.API_KEY.value, server_default=McpAuthType.API_KEY.value
    )
    auth_config_encrypted: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    discovered_tools: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(15), default=McpConnectionStatus.ACTIVE.value, server_default=McpConnectionStatus.ACTIVE.value
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
    workspace: Mapped["Workspace"] = relationship(back_populates="mcp_connections")

    def __repr__(self) -> str:
        return f"<McpConnection id={self.id!r} name={self.name!r}>"
