from enum import Enum
from typing import Optional

from pydantic import BaseModel


class CommentAuthorType(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class CommentType(str, Enum):
    MESSAGE = "message"
    INPUT_REQUEST = "input_request"
    REVIEW_FEEDBACK = "review_feedback"
    STATUS_CHANGE = "status_change"


class TaskCommentCreate(BaseModel):
    body: str
    author_type: CommentAuthorType = CommentAuthorType.HUMAN
    author_name: str = "PM"
    comment_type: CommentType = CommentType.MESSAGE
    node_id: Optional[str] = None   # which execution node this comment relates to


class TaskCommentResponse(BaseModel):
    id: str
    task_id: str
    author_type: CommentAuthorType
    author_id: Optional[str] = None
    author_name: str
    body: str
    comment_type: CommentType
    node_id: Optional[str] = None   # set for input_request comments
    iteration: int = 0
    resolved: bool = False
    created_at: str = ""
