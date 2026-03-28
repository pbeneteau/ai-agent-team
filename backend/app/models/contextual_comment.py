import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base
from app.models.enums import CommentSource

if TYPE_CHECKING:
    from app.models.artifact_version import ArtifactVersion


class ContextualComment(Base):
    __tablename__ = "contextual_comments"
    __table_args__ = (
        Index("ix_contextual_comments_version_id", "artifact_version_id"),
        Index(
            "uq_contextual_comments_external",
            "source", "external_comment_id",
            unique=True,
            postgresql_where=text("external_comment_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    artifact_version_id: Mapped[str] = mapped_column(
        Text, ForeignKey("artifact_versions.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    highlight_start: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    highlight_end: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    highlighted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), default=CommentSource.IN_APP.value, server_default=CommentSource.IN_APP.value
    )
    external_comment_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    resolved_in_version_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("artifact_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    artifact_version: Mapped["ArtifactVersion"] = relationship(
        back_populates="comments",
        foreign_keys=[artifact_version_id],
    )
    resolved_in_version: Mapped["ArtifactVersion | None"] = relationship(
        foreign_keys=[resolved_in_version_id],
    )

    def __repr__(self) -> str:
        return f"<ContextualComment id={self.id!r} version_id={self.artifact_version_id!r}>"
