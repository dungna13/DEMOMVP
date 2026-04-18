from pydantic import BaseModel
from typing import List, Optional, Dict

class Message(BaseModel):
    role: str # user, assistant
    content: str
    citations: Optional[List[Dict]] = None

class ChatRequest(BaseModel):
    message: str
    history: List[Message]
    active_source_ids: List[str]

class SummaryRequest(BaseModel):
    source_ids: List[str]
