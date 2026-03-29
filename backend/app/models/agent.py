import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base
from app.models.enums import AgentRole, AgentStatus, ModelTier, ProgressionLevel

if TYPE_CHECKING:
    from app.models.agent_skill import AgentSkill
    from app.models.workspace import Workspace


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agents_workspace_id", "workspace_id"),
        Index("ix_agents_workspace_status", "workspace_id", "status"),
        Index(
            "ix_agents_workspace_archived",
            "workspace_id",
            postgresql_where=text("archived_at IS NULL"),
        ),
        CheckConstraint(
            "readiness_score >= 0 AND readiness_score <= 100",
            name="ck_agents_readiness_score_range",
        ),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("workspaces.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialization: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(
        String(10), nullable=False, default=AgentRole.WORKER.value, server_default=AgentRole.WORKER.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AgentStatus.LEARNING.value, server_default=AgentStatus.LEARNING.value
    )
    readiness_score: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    progression_level: Mapped[str] = mapped_column(
        String(20), default=ProgressionLevel.APPRENTI.value, server_default=ProgressionLevel.APPRENTI.value
    )
    model_tier: Mapped[str] = mapped_column(
        String(10), default=ModelTier.SONNET.value, server_default=ModelTier.SONNET.value
    )
    tools: Mapped[dict | list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    completed_artifacts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    avg_quality_score: Mapped[float | None] = mapped_column(
        Numeric(3, 1), nullable=True
    )
    last_reflection_at: Mapped["datetime.datetime | None"] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped["datetime.datetime | None"] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(back_populates="agents")
    skills: Mapped[list["AgentSkill"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.id!r} name={self.name!r}>"
