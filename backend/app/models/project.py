import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.artifact import Artifact
    from app.models.document import Document
    from app.models.workspace import Workspace


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_workspace_id", "workspace_id"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("workspaces.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief_published: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    brief_published_at: Mapped["datetime.datetime | None"] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship(back_populates="projects")
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id!r} name={self.name!r}>"
