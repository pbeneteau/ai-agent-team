from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime, UTC


class ChatMessageIn(BaseModel):
    content: str
    session_id: Optional[str] = None


class ChatMessageOut(BaseModel):
    role: str
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class WSMessage(BaseModel):
    type: str
    data: Any
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
