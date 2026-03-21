"""
Pydantic schemas for request / response validation.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Conversation ──────────────────────────────────────────────────────────────

class MessageIn(BaseModel):
    """Incoming text message from the client."""

    text: str
    metadata: Optional[Dict[str, Any]] = None


class MessageOut(BaseModel):
    """Outgoing message from the AI child to the client."""

    id: int
    role: str
    content: str
    content_type: str
    timestamp: datetime
    media_url: Optional[str] = None

    model_config = {"from_attributes": True}


class ConversationHistory(BaseModel):
    messages: List[MessageOut]
    total: int


# ── Knowledge ─────────────────────────────────────────────────────────────────

class TeachIn(BaseModel):
    """User explicitly teaches the AI child something."""

    topic: str
    content: str


class KnowledgeOut(BaseModel):
    id: int
    topic: str
    content: str
    source: str
    confidence: int
    timestamp: datetime

    model_config = {"from_attributes": True}


class ToolOut(BaseModel):
    id: int
    name: str
    description: str
    code: str
    parameters_schema: Dict[str, Any]
    call_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Questions ─────────────────────────────────────────────────────────────────

class QuestionOut(BaseModel):
    id: int
    question: str
    topic: Optional[str]
    answered: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AnswerIn(BaseModel):
    answer: str


# ── WebSocket events ──────────────────────────────────────────────────────────

class WSEvent(BaseModel):
    """Generic WebSocket event envelope."""

    type: str  # "message" | "question" | "ack" | "error"
    payload: Dict[str, Any]
