"""
Database models and session management.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    JSON,
    Boolean,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


def _utcnow():
    return datetime.now(timezone.utc)


class Conversation(Base):
    """A single conversation turn between user and AI child."""

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(16), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    content_type = Column(String(32), default="text")  # text | image | audio | mixed
    media_path = Column(String(512), nullable=True)  # path to saved media file
    timestamp = Column(DateTime(timezone=True), default=_utcnow)
    metadata_ = Column("metadata", JSON, default=dict)


class KnowledgeItem(Base):
    """Explicit knowledge taught by the user."""

    __tablename__ = "knowledge"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(256), nullable=False, index=True)
    content = Column(Text, nullable=False)
    source = Column(String(64), default="user")  # "user" | "self"
    confidence = Column(Integer, default=100)  # 0-100
    timestamp = Column(DateTime(timezone=True), default=_utcnow)
    last_reviewed = Column(DateTime(timezone=True), nullable=True)


class PendingQuestion(Base):
    """Questions the AI child wants to ask the user."""

    __tablename__ = "pending_questions"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    topic = Column(String(256), nullable=True)
    answered = Column(Boolean, default=False)
    answer = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    answered_at = Column(DateTime(timezone=True), nullable=True)


class Tool(Base):
    """A reusable Python tool created by the AI child."""

    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False)
    code = Column(Text, nullable=False)
    # OpenAI-style JSON schema describing the tool's parameters
    parameters_schema = Column(JSON, nullable=False, default=dict)
    call_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow)


async def init_db():
    """Create all tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    """FastAPI dependency that provides a database session."""
    async with async_session() as session:
        yield session
