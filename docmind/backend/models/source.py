from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any

class SourceMeta(BaseModel):
    url: Optional[str] = None
    page_count: Optional[int] = None
    language: Optional[str] = "en"
    local_path: Optional[str] = None # Path to original saved file

class Source(BaseModel):
    id: str
    name: str
    type: str  # pdf, url, text
    active: bool = True
    chunk_count: int = 0
    word_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    meta: SourceMeta = Field(default_factory=SourceMeta)

class SourceCreate(BaseModel):
    name: str
    type: str
    content: str  # Base64 or plain text

class SourceUpdate(BaseModel):
    active: Optional[bool] = None
    name: Optional[str] = None

class URLSourceCreate(BaseModel):
    url: str
    name: Optional[str] = None
