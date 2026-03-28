import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base
from app.models.enums import SkillCategory

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.artifact import Artifact


class AgentSkill(Base):
    __tablename__ = "agent_skills"
    __table_args__ = (
        Index("ix_agent_skills_agent_id", "agent_id"),
        Index("ix_agent_skills_agent_category", "agent_id", "category"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    agent_id: Mapped[str] = mapped_column(
        Text, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_artifact_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship(back_populates="skills")
    source_artifact: Mapped["Artifact | None"] = relationship(
        foreign_keys=[source_artifact_id]
    )

    def __repr__(self) -> str:
        return f"<AgentSkill id={self.id!r} title={self.title!r}>"
