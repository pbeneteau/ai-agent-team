import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base
from app.models.enums import ArtifactStatus, ArtifactType

if TYPE_CHECKING:
    from app.models.artifact_version import ArtifactVersion
    from app.models.execution_wave import ExecutionWave
    from app.models.project import Project


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_project_id", "project_id"),
        Index("ix_artifacts_project_status", "project_id", "status"),
        Index(
            "ix_artifacts_git_pr",
            "git_pr_url",
            postgresql_where=text("git_pr_url IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(15), nullable=False, default=ArtifactStatus.DRAFTING.value, server_default=ArtifactStatus.DRAFTING.value
    )
    max_budget_usd: Mapped[float] = mapped_column(
        Numeric(10, 2), default=5.00, server_default="5.00"
    )
    total_cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 2), default=0.00, server_default="0.00"
    )
    current_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    git_repo_url: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    git_base_branch: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    git_feature_branch: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    git_pr_url: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    git_pr_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    cancelled_at: Mapped["datetime.datetime | None"] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped["datetime.datetime | None"] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="artifacts")
    versions: Mapped[list["ArtifactVersion"]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )
    execution_waves: Mapped[list["ExecutionWave"]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Artifact id={self.id!r} title={self.title!r}>"
