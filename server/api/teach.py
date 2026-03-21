"""
Teaching and knowledge management endpoints.
"""
import asyncio
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai.child import incorporate_teaching
from ai.memory import (
    add_knowledge,
    answer_question,
    get_all_knowledge,
    get_unanswered_questions,
)
from ai.profile import NAME_QUESTION_TOPIC, extract_name_from_answer, set_ai_name
from ai.researcher import research_topic
from ai.tools import get_all_tools, get_tool
from models import get_session
from models.schemas import AnswerIn, KnowledgeOut, QuestionOut, TeachIn, ToolOut

router = APIRouter(prefix="/teach", tags=["teach"])


@router.post("/", response_model=dict)
async def teach(
    body: TeachIn,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Explicitly teach the AI child a new piece of knowledge.

    After acknowledging the lesson, the AI autonomously searches the web for
    more information on the topic (background task — does not delay the reply).
    """
    await add_knowledge(session, topic=body.topic, content=body.content)
    reply = await incorporate_teaching(session, body.topic, body.content)
    # Autonomous follow-up research
    background_tasks.add_task(research_topic, body.topic, body.content)
    return {"reply": reply}


@router.get("/knowledge", response_model=List[KnowledgeOut])
async def list_knowledge(session: AsyncSession = Depends(get_session)):
    """Return all knowledge items the AI child has been taught or researched."""
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
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    Answer a question the AI child has asked.

    Special case — naming question (topic "__name__"):
      The AI extracts its name from the answer and stores it permanently.
      No research is triggered (naming doesn't need web search).

    All other questions:
      The answer is stored as user-sourced knowledge, the AI acknowledges it,
      and an autonomous web-research task is launched in the background.
    """
    q = await answer_question(session, question_id, body.answer)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")

    # ── Special: naming question ──────────────────────────────────────────────
    if q.topic == NAME_QUESTION_TOPIC:
        name = await extract_name_from_answer(body.answer)
        await set_ai_name(session, name)
        reply = (
            f"太好了！以后我就叫{name}了！"
            f"谢谢你给我起了这么好听的名字！😊"
            f"我们继续聊吧，我还有好多想问你的问题！"
        )
        return {"reply": reply}

    # ── Normal question ───────────────────────────────────────────────────────
    topic = q.topic or q.question[:64]

    # Store the answer as user-sourced knowledge
    await add_knowledge(session, topic=topic, content=body.answer, source="user")

    # Acknowledge via conversation
    reply = await incorporate_teaching(session, topic=topic, content=body.answer)

    # Launch autonomous web research (non-blocking)
    background_tasks.add_task(research_topic, topic, body.answer)

    return {"reply": reply}


# ── Tool endpoints ─────────────────────────────────────────────────────────────

@router.get("/tools", response_model=List[ToolOut])
async def list_tools(session: AsyncSession = Depends(get_session)):
    """Return all reusable tools the AI child has created."""
    tools = await get_all_tools(session)
    return [
        ToolOut(
            id=t.id,
            name=t.name,
            description=t.description,
            code=t.code,
            parameters_schema=t.parameters_schema,
            call_count=t.call_count,
            created_at=t.created_at,
        )
        for t in tools
    ]


@router.get("/tools/{name}", response_model=ToolOut)
async def get_tool_by_name(name: str, session: AsyncSession = Depends(get_session)):
    """Return details of a specific tool by name."""
    tool = await get_tool(session, name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")
    return ToolOut(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        code=tool.code,
        parameters_schema=tool.parameters_schema,
        call_count=tool.call_count,
        created_at=tool.created_at,
    )

