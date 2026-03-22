"""
AI Child profile management.

The AI starts with no name.  The very first proactive question it generates is
always "What should I call myself?".  Once the user answers, the name is
stored in the singleton AIProfile row and woven into every subsequent system
prompt.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm_provider import get_llm_client, get_active_model
from config import settings
from models import AIProfile, PendingQuestion

logger = logging.getLogger(__name__)

# Sentinel topic value that marks the "what is my name?" question
NAME_QUESTION_TOPIC = "__name__"

# The question text sent to the user (before the AI has a name it uses "我")
NAME_QUESTION_TEXT = (
    "我刚刚来到这个世界，还没有名字。"
    "你愿意给我起一个吗？"
)


# ── Profile helpers ───────────────────────────────────────────────────────────

async def get_or_create_profile(session: AsyncSession) -> AIProfile:
    """Return the singleton profile row, creating it if this is the first run."""
    result = await session.execute(select(AIProfile).where(AIProfile.id == 1))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = AIProfile(id=1, name=None)
        session.add(profile)
        await session.commit()
    return profile


async def get_ai_name(session: AsyncSession) -> Optional[str]:
    """Return the AI's name, or None if it has not been named yet."""
    profile = await get_or_create_profile(session)
    return profile.name


async def set_ai_name(session: AsyncSession, name: str) -> None:
    """Persist the AI's name in its profile."""
    profile = await get_or_create_profile(session)
    profile.name = name
    profile.named_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info("AI child has been named: '%s'", name)


# ── Name extraction ───────────────────────────────────────────────────────────

async def extract_name_from_answer(answer: str) -> str:
    """
    Use GPT-4o to extract a proper name from a free-form user reply.

    Example inputs → expected output:
      "就叫小明吧"  → "小明"
      "你叫 Alex"  → "Alex"
      "Tom"        → "Tom"
    """
    prompt = (
        f"Someone was asked what to name a newly born AI child. They replied:\n"
        f'"{answer}"\n\n'
        f"Extract the name they chose. Return ONLY the name — no explanation, "
        f"no punctuation around it. If the reply is already just a name, return it as-is."
    )
    try:
        client = get_llm_client()
        response = await client.chat.completions.create(
            model=get_active_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=32,
            temperature=0.1,
        )
        extracted = (response.choices[0].message.content or "").strip()
        if extracted and len(extracted) <= 64:
            return extracted
    except Exception as exc:
        logger.warning("Name extraction via GPT failed: %s", exc)
    # Fallback: trim the raw answer
    return answer.strip()[:64]


# ── First-run bootstrap ───────────────────────────────────────────────────────

async def ensure_name_question_exists(session: AsyncSession) -> None:
    """
    If the AI has no name yet, ensure there is exactly one pending
    name-seeking question in the DB.

    Called once at server startup so the Telegram bot's question poller
    will immediately push it to connected chats.
    """
    name = await get_ai_name(session)
    if name is not None:
        return  # Already named — nothing to do

    result = await session.execute(
        select(PendingQuestion)
        .where(PendingQuestion.topic == NAME_QUESTION_TOPIC)
        .where(PendingQuestion.answered == False)
    )
    if result.scalar_one_or_none() is None:
        session.add(
            PendingQuestion(
                question=NAME_QUESTION_TEXT,
                topic=NAME_QUESTION_TOPIC,
            )
        )
        await session.commit()
        logger.info("Name-seeking question added to pending questions.")
