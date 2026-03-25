from typing import Optional

from pydantic import BaseModel


class LabelCreate(BaseModel):
    name: str
    color: str = "#8b5cf6"
    group: Optional[str] = None
    description: Optional[str] = None


class LabelResponse(BaseModel):
    id: str
    name: str
    color: str = "#8b5cf6"
    group: Optional[str] = None
    description: Optional[str] = None
    created_at: str = ""
