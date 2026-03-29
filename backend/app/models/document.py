import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base
from app.models.enums import ProcessingStatus

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk
    from app.models.project import Project
    from app.models.workspace import Workspace


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_project_id", "project_id"),
        Index("ix_documents_workspace_id", "workspace_id"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    s3_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    processing_status: Mapped[str] = mapped_column(
        String(15), default=ProcessingStatus.PENDING.value, server_default=ProcessingStatus.PENDING.value
    )
    created_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    project: Mapped["Project | None"] = relationship(back_populates="documents")
    workspace: Mapped["Workspace | None"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id!r} filename={self.filename!r}>"
