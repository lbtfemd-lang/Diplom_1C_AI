from pydantic import BaseModel
from typing import List, Optional

class Message(BaseModel):
    role: str
    text: str

ChatMessage = Message

class ChatRequest(BaseModel):
    messages: List[Message]
    context: Optional[str] = None
    temperature: Optional[float] = 0.6
    user_identity: Optional[str] = None
    user_role: Optional[str] = None

class OpenFormAction(BaseModel):
    form_name: str
    params: Optional[dict] = None

class CreateTaskAction(BaseModel):
    title: str
    description: Optional[str] = None
    column: Optional[str] = "todo"
    priority: Optional[str] = "normal"
    assignee: Optional[str] = None
    due_date: Optional[str] = None

class ShowReportAction(BaseModel):
    report_name: str
    parameters: Optional[dict] = None

class DraftOrderAction(BaseModel):
    document_type: str = "ЗаказПоставщику"
    supplier: Optional[str] = None
    total_amount: Optional[float] = 0.0
    items: Optional[List[dict]] = None

class ChatResponse(BaseModel):
    role: str
    text: str
    action: Optional[str] = None
    data: Optional[dict] = None
    user_identity: Optional[str] = None
    requires_confirmation: bool = False
    provider_used: Optional[str] = "offline_rules"
    is_fallback: bool = False
    model_name: Optional[str] = "offline-rule-engine"

class MetadataItem(BaseModel):
    name: str
    synonym: str
    fields: Optional[List[dict]] = None

class MetadataRequest(BaseModel):
    items: List[MetadataItem]

class VoiceTranscribeRequest(BaseModel):
    audio_base64: str
    format: Optional[str] = "webm"
    language: Optional[str] = "ru"

class VoiceTranscribeResponse(BaseModel):
    text: str
    confidence: Optional[float] = 1.0
    detected_language: Optional[str] = "ru"
    error: Optional[str] = None


