"""SQLAlchemy domain models for the Artifact-First architecture (Vision 2.0).

Tables:
  - projects
  - artifacts
  - artifact_versions
  - contextual_comments
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ArtifactStatus(str, enum.Enum):
    DRAFTING = "drafting"
    IN_REVIEW = "in_review"
    APPROVED = "approved"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Project id={self.id!r} name={self.name!r}>"


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ArtifactStatus] = mapped_column(
        Enum(ArtifactStatus, name="artifact_status", values_callable=lambda e: [m.value for m in e]),
        default=ArtifactStatus.DRAFTING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="artifacts")
    versions: Mapped[list["ArtifactVersion"]] = relationship(back_populates="artifact", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Artifact id={self.id!r} title={self.title!r} status={self.status.value}>"


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    token_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    artifact: Mapped["Artifact"] = relationship(back_populates="versions")
    comments: Mapped[list["ContextualComment"]] = relationship(back_populates="artifact_version", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ArtifactVersion id={self.id!r} v{self.version_number}>"


class ContextualComment(Base):
    __tablename__ = "contextual_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    artifact_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artifact_versions.id", ondelete="CASCADE"), nullable=False
    )
    highlighted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    artifact_version: Mapped["ArtifactVersion"] = relationship(back_populates="comments")

    def __repr__(self) -> str:
        return f"<ContextualComment id={self.id!r} resolved={self.resolved}>"
