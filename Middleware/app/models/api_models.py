from pydantic import BaseModel
from typing import List, Optional

class Message(BaseModel):
    role: str
    text: str

class ChatRequest(BaseModel):
    messages: List[Message]
    context: Optional[str] = None
    temperature: Optional[float] = 0.6

class ChatResponse(BaseModel):
    role: str
    text: str
    action: Optional[str] = None
    data: Optional[dict] = None

class MetadataItem(BaseModel):
    name: str
    synonym: str
    fields: Optional[List[dict]] = None

class MetadataRequest(BaseModel):
    items: List[MetadataItem]

