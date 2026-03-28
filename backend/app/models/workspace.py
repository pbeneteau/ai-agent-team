import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.git_provider_connection import GitProviderConnection
    from app.models.mcp_connection import McpConnection
    from app.models.project import Project


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    monthly_budget_usd: Mapped[float] = mapped_column(
        Numeric(10, 2), default=50.00, server_default="50.00"
    )
    monthly_spend_usd: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0.00, server_default="0.00"
    )
    billing_period_start: Mapped["datetime.datetime | None"] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    created_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agents: Mapped[list["Agent"]] = relationship(back_populates="workspace")
    projects: Mapped[list["Project"]] = relationship(back_populates="workspace")
    git_provider_connections: Mapped[list["GitProviderConnection"]] = relationship(
        back_populates="workspace"
    )
    mcp_connections: Mapped[list["McpConnection"]] = relationship(
        back_populates="workspace"
    )

    def __repr__(self) -> str:
        return f"<Workspace id={self.id!r} name={self.name!r}>"
