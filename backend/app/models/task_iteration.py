from enum import Enum
from typing import Optional

from pydantic import BaseModel


class IterationTrigger(str, Enum):
    INITIAL = "initial"
    REVIEW_FEEDBACK = "review_feedback"
    INPUT_PROVIDED = "input_provided"
    MANUAL_RERUN = "manual_rerun"


class TaskIterationResponse(BaseModel):
    id: str
    task_id: str
    iteration_number: int
    trigger: IterationTrigger
    feedback: Optional[str] = None
    started_at: str = ""
    completed_at: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    result_summary: Optional[str] = None
