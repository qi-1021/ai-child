"""
Memory management – stores and retrieves conversation history
and explicit knowledge in the SQLite database.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Conversation, KnowledgeItem, PendingQuestion


# ── Conversation history ──────────────────────────────────────────────────────

async def add_message(
    session: AsyncSession,
    role: str,
    content: str,
    content_type: str = "text",
    media_path: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Conversation:
    msg = Conversation(
        role=role,
        content=content,
        content_type=content_type,
        media_path=media_path,
        metadata_=metadata or {},
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def get_recent_messages(
    session: AsyncSession, limit: int = 20
) -> List[Conversation]:
    result = await session.execute(
        select(Conversation).order_by(Conversation.timestamp.desc()).limit(limit)
    )
    rows = result.scalars().all()
    return list(reversed(rows))


async def count_messages(session: AsyncSession) -> int:
    result = await session.execute(select(Conversation))
    return len(result.scalars().all())


# ── Knowledge base ────────────────────────────────────────────────────────────

async def add_knowledge(
    session: AsyncSession,
    topic: str,
    content: str,
    source: str = "user",
    confidence: int = 100,
) -> KnowledgeItem:
    item = KnowledgeItem(
        topic=topic,
        content=content,
        source=source,
        confidence=confidence,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def get_all_knowledge(session: AsyncSession) -> List[KnowledgeItem]:
    result = await session.execute(
        select(KnowledgeItem).order_by(KnowledgeItem.timestamp.desc())
    )
    return result.scalars().all()


async def search_knowledge(
    session: AsyncSession, query: str
) -> List[KnowledgeItem]:
    """Search for knowledge with relevance filtering."""
    result = await session.execute(
        select(KnowledgeItem).where(
            KnowledgeItem.topic.ilike(f"%{query}%")
            | KnowledgeItem.content.ilike(f"%{query}%")
        )
    )
    return result.scalars().all()


async def get_high_quality_knowledge(
    session: AsyncSession, min_confidence: int = 70, limit: int = 10
) -> List[KnowledgeItem]:
    """✅ OPTIMIZATION: Get only high-quality knowledge (confidence >= min_confidence)."""
    result = await session.execute(
        select(KnowledgeItem)
        .where(KnowledgeItem.confidence >= min_confidence)
        .order_by(KnowledgeItem.confidence.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ── Pending questions ─────────────────────────────────────────────────────────

async def add_pending_question(
    session: AsyncSession, question: str, topic: Optional[str] = None
) -> PendingQuestion:
    q = PendingQuestion(question=question, topic=topic)
    session.add(q)
    await session.commit()
    await session.refresh(q)
    return q


async def get_unanswered_questions(
    session: AsyncSession,
) -> List[PendingQuestion]:
    result = await session.execute(
        select(PendingQuestion)
        .where(PendingQuestion.answered == False)  # noqa: E712
        .order_by(PendingQuestion.created_at.asc())
    )
    return result.scalars().all()


async def answer_question(
    session: AsyncSession, question_id: int, answer: str
) -> Optional[PendingQuestion]:
    result = await session.execute(
        select(PendingQuestion).where(PendingQuestion.id == question_id)
    )
    q = result.scalar_one_or_none()
    if q is None:
        return None
    q.answered = True
    q.answer = answer
    q.answered_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(q)
    return q
