import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.artifact import Artifact
    from app.models.contextual_comment import ContextualComment
    from app.models.execution_wave import ExecutionWave


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        Index("ix_artifact_versions_artifact_id", "artifact_id"),
        UniqueConstraint(
            "artifact_id", "version_number",
            name="uq_artifact_versions_artifact_version",
        ),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    artifact_id: Mapped[str] = mapped_column(
        Text, ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_prefix: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_manifest: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    token_cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 4), default=0, server_default="0"
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    assumptions: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    sources: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    execution_wave_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("execution_waves.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    artifact: Mapped["Artifact"] = relationship(back_populates="versions")
    execution_wave: Mapped["ExecutionWave | None"] = relationship(
        back_populates="produced_version"
    )
    comments: Mapped[list["ContextualComment"]] = relationship(
        back_populates="artifact_version",
        foreign_keys="ContextualComment.artifact_version_id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ArtifactVersion id={self.id!r} artifact_id={self.artifact_id!r} v{self.version_number}>"
