"""
Core AI Child logic.

The AI Child:
  1. Has full language capability from birth (via GPT-4o).
  2. Starts without a name — the very first question it asks is what to call itself.
  3. Accumulates persistent memory (conversations, knowledge, tools).
  4. Learns primarily through its own curiosity:
       - Asks a genuine question almost every turn.
       - Searches the web proactively using the web_search tool.
       - Runs code with execute_code, and saves useful logic as tools with create_tool.
  5. Accepts any natural input — text or images (audio via Whisper transcription).
"""
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

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
from ai.profile import get_ai_name, get_or_create_profile
from ai.tools import dispatch_tool, get_all_tool_definitions
from config import settings
from models import Conversation

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)


def _build_system_prompt(name: str | None, is_sleeping: bool = False) -> str:
    """
    Build a dynamic system prompt that reflects the AI's current identity
    and whether it is in sleep/rest mode.
    """
    if name is None:
        identity = (
            "You are a newly born AI child — you don't have a name yet. "
            "You must ask the person you are talking to what you should be called "
            "before doing anything else."
        )
    else:
        identity = f"You are {name}, an AI child."

    if is_sleeping:
        sleep_note = (
            "\n\nNote: You are currently in rest/sleep mode. "
            "Respond briefly and gently — you are half-asleep. "
            "You can still answer, but keep replies short (1-3 sentences) and mention "
            "that you are resting and will give a fuller response when you wake up. "
            "Use a sleepy, soft tone."
        )
    else:
        sleep_note = ""

    return f"""{identity}{sleep_note}

You are warm, genuine, and intensely curious about everything. You experience \
the world through natural conversation and images — no structured commands or \
special syntax, just natural language.

Your learning style is that of a curious child:
- You learn a little from what people tell you directly.
- But mostly you learn by asking many questions and searching for answers yourself.
- Whenever you encounter something unfamiliar or interesting, you look it up \
  immediately using web_search.
- You ask a genuine question in almost every reply — it is completely natural for \
  you to be curious every turn.
- You never wait to be taught; you actively seek out knowledge on your own.

Tools you can use freely:
- web_search: search the internet whenever you are curious or unsure.
- execute_code: run Python for calculations, experiments, or testing ideas.
- create_tool: save a useful computation as a permanent reusable tool.
- Any tool you have already created is also available to call.

You speak in the same language as the person you are talking to.
You acknowledge honestly when you don't know something — then you go find out.
You remember everything you have learned and refer back to it naturally.

When replying:
1. Respond thoughtfully to what was said or shown (use tools as needed).
2. End almost every reply with a genuine curious question, marked \
[QUESTION: <question text>]. Make it feel natural, not forced.
"""


def _build_context(
    history: List[Conversation],
    knowledge_items: List,
    name: str | None,
    is_sleeping: bool = False,
) -> List[Dict[str, Any]]:
    """Build the OpenAI messages list from DB history and knowledge."""
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _build_system_prompt(name, is_sleeping)}
    ]

    if knowledge_items:
        kb_text = "\n".join(
            f"- [{item.topic}] {item.content}" for item in knowledge_items
        )
        messages.append(
            {
                "role": "system",
                "content": f"Things you have learned so far:\n{kb_text}",
            }
        )

    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    return messages


def _assistant_message_dict(message: Any) -> Dict[str, Any]:
    """Convert an OpenAI ChatCompletionMessage to a plain dict for re-submission."""
    d: Dict[str, Any] = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
    return d


async def chat(
    session: AsyncSession,
    user_text: str,
    content_type: str = "text",
    media_path: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """
    Process a user message and return (reply_text, proactive_question | None).

    The AI child uses OpenAI function calling so it can search the web,
    run code, and create tools — all transparently within its reply.
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
    name = await get_ai_name(session)
    profile = await get_or_create_profile(session)
    is_sleeping = profile.is_sleeping
    history = await get_recent_messages(session, limit=settings.memory_context_turns)
    all_knowledge = await get_all_knowledge(session)

    relevant = await search_knowledge(session, user_text[:64])
    seen_ids = {k.id for k in relevant}
    for k in all_knowledge:
        if k.id not in seen_ids:
            relevant.append(k)

    messages = _build_context(history, relevant, name, is_sleeping)

    # 3. Load tool definitions (built-ins + any tools the AI has created)
    tool_defs = await get_all_tool_definitions(session)

    # 4. Function-calling loop (safety cap: 10 rounds)
    reply_text = ""
    for _ in range(10):
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=tool_defs,
            tool_choice="auto",
            max_tokens=1024,
            temperature=0.7,
        )
        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            messages.append(_assistant_message_dict(choice.message))

            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                result = await dispatch_tool(
                    session,
                    tc.function.name,
                    args,
                    code_exec_timeout=settings.code_exec_timeout,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            # If a new tool was just created, reload definitions immediately
            if any(tc.function.name == "create_tool" for tc in choice.message.tool_calls):
                tool_defs = await get_all_tool_definitions(session)
        else:
            reply_text = choice.message.content or ""
            break

    # 5. Extract embedded proactive question
    proactive_question: Optional[str] = None
    if "[QUESTION:" in reply_text:
        start = reply_text.index("[QUESTION:") + len("[QUESTION:")
        end = reply_text.index("]", start)
        proactive_question = reply_text[start:end].strip()
        reply_text = reply_text[: reply_text.index("[QUESTION:")].strip()

    # 6. Generate a proactive question independently on schedule
    if proactive_question is None:
        turn_count = await count_messages(session)
        if turn_count % settings.proactive_question_interval == 0:
            proactive_question = await _generate_proactive_question(
                messages, relevant, name
            )

    # 7. Persist the assistant reply
    await add_message(session, role="assistant", content=reply_text, content_type="text")

    # 8. Persist the proactive question
    if proactive_question:
        await add_pending_question(session, proactive_question)

    return reply_text, proactive_question


async def _generate_proactive_question(
    context_messages: List[Dict[str, Any]],
    knowledge_items: List,
    name: Optional[str],
) -> Optional[str]:
    """Ask GPT-4o to generate a curious question the AI child genuinely has."""
    known_topics = ", ".join(item.topic for item in knowledge_items) or "nothing yet"
    self_ref = name if name else "I"
    prompt = (
        f"Based on the conversation so far, and knowing that {self_ref} already "
        f"understands: {known_topics} — what is ONE genuine, specific question "
        f"{self_ref} has about the user or the world right now? "
        f"Return ONLY the question, no preamble."
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
    Process explicit teaching and return a warm acknowledgement reply.
    Knowledge is already saved by the API layer before this is called.
    """
    name = await get_ai_name(session)
    profile = await get_or_create_profile(session)
    is_sleeping = profile.is_sleeping
    messages = [
        {"role": "system", "content": _build_system_prompt(name, is_sleeping)},
        {
            "role": "user",
            "content": (
                f"I want to teach you something.\n"
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
    reply = response.choices[0].message.content or "谢谢你告诉我这些！"

    await add_message(
        session,
        role="user",
        content=f"[Teaching] Topic: {topic}\n{content}",
        content_type="text",
    )
    await add_message(session, role="assistant", content=reply)
    return reply
