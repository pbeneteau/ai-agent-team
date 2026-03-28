import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime

from app.core.database import Base
from app.models.enums import WaveStatus, WaveTrigger

if TYPE_CHECKING:
    from app.models.artifact import Artifact
    from app.models.artifact_version import ArtifactVersion
    from app.models.contextual_comment import ContextualComment


class ExecutionWave(Base):
    __tablename__ = "execution_waves"
    __table_args__ = (
        Index("ix_execution_waves_artifact_id", "artifact_id"),
        Index(
            "ix_execution_waves_status",
            "status",
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    artifact_id: Mapped[str] = mapped_column(
        Text, ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False
    )
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_comment_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("contextual_comments.id", ondelete="SET NULL"), nullable=True
    )
    dag_plan: Mapped[dict] = mapped_column(JSONB, nullable=False)
    assembled_team: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(15), nullable=False, default=WaveStatus.QUEUED.value, server_default=WaveStatus.QUEUED.value
    )
    current_step: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    total_steps: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    step_labels: Mapped[list] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 4), default=0, server_default="0"
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped["datetime.datetime | None"] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped["datetime.datetime | None"] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped["datetime.datetime"] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    artifact: Mapped["Artifact"] = relationship(back_populates="execution_waves")
    trigger_comment: Mapped["ContextualComment | None"] = relationship(
        foreign_keys=[trigger_comment_id]
    )
    produced_version: Mapped["ArtifactVersion | None"] = relationship(
        back_populates="execution_wave"
    )

    def __repr__(self) -> str:
        return f"<ExecutionWave id={self.id!r} artifact_id={self.artifact_id!r} status={self.status!r}>"
