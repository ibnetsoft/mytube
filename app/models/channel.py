"""
Channel Pydantic Models
"""

from pydantic import BaseModel
from typing import Optional, Any


class ChannelCreate(BaseModel):
    name: str
    handle: str
    description: Optional[str] = None


class ChannelResponse(BaseModel):
    id: int
    name: str
    handle: str
    description: Optional[str]
    created_at: Any
    credentials_path: Optional[str] = None
