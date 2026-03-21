"""
Teaching and knowledge management endpoints.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai.child import incorporate_teaching
from ai.memory import (
    add_knowledge,
    answer_question,
    get_all_knowledge,
    get_unanswered_questions,
)
from models import get_session
from models.schemas import AnswerIn, KnowledgeOut, QuestionOut, TeachIn

router = APIRouter(prefix="/teach", tags=["teach"])


@router.post("/", response_model=dict)
async def teach(
    body: TeachIn,
    session: AsyncSession = Depends(get_session),
):
    """
    Explicitly teach the AI child a new piece of knowledge.
    The AI child stores the knowledge and replies with an acknowledgement.
    """
    await add_knowledge(session, topic=body.topic, content=body.content)
    reply = await incorporate_teaching(session, body.topic, body.content)
    return {"reply": reply}


@router.get("/knowledge", response_model=List[KnowledgeOut])
async def list_knowledge(session: AsyncSession = Depends(get_session)):
    """Return all knowledge items the AI child has been taught."""
    items = await get_all_knowledge(session)
    return [
        KnowledgeOut(
            id=i.id,
            topic=i.topic,
            content=i.content,
            source=i.source,
            confidence=i.confidence,
            timestamp=i.timestamp,
        )
        for i in items
    ]


@router.get("/questions", response_model=List[QuestionOut])
async def list_questions(session: AsyncSession = Depends(get_session)):
    """Return all unanswered questions the AI child has asked."""
    questions = await get_unanswered_questions(session)
    return [
        QuestionOut(
            id=q.id,
            question=q.question,
            topic=q.topic,
            answered=q.answered,
            created_at=q.created_at,
        )
        for q in questions
    ]


@router.post("/questions/{question_id}/answer", response_model=dict)
async def answer(
    question_id: int,
    body: AnswerIn,
    session: AsyncSession = Depends(get_session),
):
    """Answer a question the AI child has asked."""
    q = await answer_question(session, question_id, body.answer)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")

    # Store the answer as knowledge
    await add_knowledge(
        session,
        topic=q.topic or q.question[:64],
        content=body.answer,
        source="user",
    )

    # Acknowledge via conversation
    reply = await incorporate_teaching(
        session,
        topic=q.topic or q.question[:64],
        content=body.answer,
    )
    return {"reply": reply}
