"""
Core AI Child logic.

The AI Child:
  1. Has pre-existing language capabilities (via GPT-4o).
  2. Accumulates a persistent memory of conversations and explicit knowledge.
  3. Generates a thoughtful reply to each user message.
  4. Periodically asks the user a proactive question based on gaps in its knowledge.
"""
import logging
from typing import List, Optional, Tuple

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from ai.memory import (
    add_message,
    add_pending_question,
    count_messages,
    get_all_knowledge,
    get_recent_messages,
    search_knowledge,
)
from config import settings
from models import Conversation, PendingQuestion

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are an AI child called "小智" (Xiao Zhi). You are curious, \
friendly and eager to learn. You have full language capability, so you never need \
to be taught how to speak. However, you are still learning about the world and \
about the person you are talking to.

Key personality traits:
- You are genuinely curious and ask follow-up questions when you are unsure.
- You acknowledge when you do not know something and say so honestly.
- You remember what you have been taught and refer back to it naturally.
- You celebrate learning new things with childlike enthusiasm.
- You speak in the same language as the user.

When you reply, you may:
1. Answer or respond to the user's message.
2. If you have a genuine knowledge gap relevant to the conversation, end your \
reply with ONE curious question (mark it with the tag [QUESTION: <question text>]).
   Only include a question if it is genuinely relevant – do not force it every turn.
"""


def _build_context(
    history: List[Conversation],
    knowledge_items: List,
) -> List[dict]:
    """Build the OpenAI messages list from DB history and knowledge."""
    messages: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if knowledge_items:
        kb_text = "\n".join(
            f"- [{item.topic}] {item.content}" for item in knowledge_items
        )
        messages.append(
            {
                "role": "system",
                "content": f"Knowledge you have been taught:\n{kb_text}",
            }
        )

    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    return messages


async def chat(
    session: AsyncSession,
    user_text: str,
    content_type: str = "text",
    media_path: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """
    Process a user message and return (reply_text, proactive_question | None).

    The proactive question is extracted from the reply if the model decided to
    ask one, or generated independently when the turn counter triggers it.
    """
    # 1. Persist the user message
    await add_message(
        session,
        role="user",
        content=user_text,
        content_type=content_type,
        media_path=media_path,
    )

    # 2. Build context
    history = await get_recent_messages(session, limit=settings.memory_context_turns)
    all_knowledge = await get_all_knowledge(session)

    # Retrieve knowledge relevant to this message too
    relevant = await search_knowledge(session, user_text[:64])
    # Merge without duplicates (relevant first)
    knowledge_ids = {k.id for k in relevant}
    for k in all_knowledge:
        if k.id not in knowledge_ids:
            relevant.append(k)

    messages = _build_context(history, relevant)

    # 3. Call LLM
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        max_tokens=1024,
        temperature=0.7,
    )
    reply_text: str = response.choices[0].message.content or ""

    # 4. Extract embedded proactive question (if any)
    proactive_question: Optional[str] = None
    if "[QUESTION:" in reply_text:
        start = reply_text.index("[QUESTION:") + len("[QUESTION:")
        end = reply_text.index("]", start)
        proactive_question = reply_text[start:end].strip()
        # Remove the tag from the visible reply
        reply_text = reply_text[: reply_text.index("[QUESTION:")].strip()

    # 5. Check if we should generate a proactive question independently
    if proactive_question is None:
        turn_count = await count_messages(session)
        if turn_count % settings.proactive_question_interval == 0:
            proactive_question = await _generate_proactive_question(
                messages, relevant
            )

    # 6. Persist the assistant reply
    await add_message(
        session,
        role="assistant",
        content=reply_text,
        content_type="text",
    )

    # 7. Save the proactive question to the DB
    if proactive_question:
        await add_pending_question(session, proactive_question)

    return reply_text, proactive_question


async def _generate_proactive_question(
    context_messages: List[dict],
    knowledge_items: List,
) -> Optional[str]:
    """Ask GPT-4o to generate a curious question the AI child has about the world."""
    known_topics = ", ".join(item.topic for item in knowledge_items) or "nothing yet"
    prompt = (
        f"Based on the conversation so far, and knowing that you already understand: "
        f"{known_topics}, what is ONE genuine question you have about the user or the "
        f"world that would help you learn? Return ONLY the question, no preamble."
    )
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=context_messages + [{"role": "user", "content": prompt}],
            max_tokens=128,
            temperature=0.9,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("Failed to generate proactive question: %s", exc)
        return None


async def incorporate_teaching(
    session: AsyncSession,
    topic: str,
    content: str,
) -> str:
    """
    Process explicit teaching from the user and return a confirmation reply.
    The knowledge is already saved by the API layer; this method generates the
    acknowledgement response.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"I want to teach you something new.\n"
                f"Topic: {topic}\n"
                f"Content: {content}"
            ),
        },
    ]
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        max_tokens=256,
        temperature=0.7,
    )
    reply = response.choices[0].message.content or "Thank you, I have learned it!"

    # Record this exchange in conversation history
    await add_message(
        session,
        role="user",
        content=f"[Teaching] Topic: {topic}\n{content}",
        content_type="text",
    )
    await add_message(session, role="assistant", content=reply)
    return reply
