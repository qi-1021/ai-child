"""
Core AI Child logic.

The AI Child:
  1. Has full language capability from birth (via GPT-4o 或其他 LLM).
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

from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm_provider import get_llm_client
from ai.memory import (
    add_message,
    add_pending_question,
    count_messages,
    get_all_knowledge,
    get_recent_messages,
    search_knowledge,
    get_high_quality_knowledge,
)
from ai.profile import get_ai_name, get_or_create_profile
from ai.personality_memory import PersonalityMemoryManager
from ai.tools import dispatch_tool, get_all_tool_definitions
from config import settings
from i18n.messages import build_system_prompt
from models import Conversation

logger = logging.getLogger(__name__)


async def _build_context_with_personality(
    session: AsyncSession,
    history: List[Conversation],
    knowledge_items: List,
    name: str | None,
    is_sleeping: bool = False,
    language: str = "en-US",
) -> List[Dict[str, Any]]:
    """Build the OpenAI messages list from DB history, knowledge, and personality."""
    personality_manager = PersonalityMemoryManager(session)
    personality_context = await personality_manager.build_personality_context()

    system_prompt = build_system_prompt(name, is_sleeping, language)
    if personality_context:
        system_prompt = f"{system_prompt}\n\n{personality_context}"

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt}
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
    language = getattr(profile, "preferred_language", "en-US") or "en-US"
    history = await get_recent_messages(session, limit=settings.memory_context_turns)

    # Semantic search for relevant knowledge; fall back to high-quality items
    relevant = await search_knowledge(session, user_text[:64])
    relevant = sorted(relevant, key=lambda k: k.confidence, reverse=True)[:10]
    if not relevant:
        relevant = await get_high_quality_knowledge(session)

    messages = await _build_context_with_personality(
        session, history, relevant, name, is_sleeping, language
    )

    # 3. Load tool definitions (built-ins + any tools the AI has created)
    tool_defs = await get_all_tool_definitions(session)

    # 4. Function-calling loop (safety cap: 10 rounds)
    client = get_llm_client()
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
        client = get_llm_client()
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
    language = getattr(profile, "preferred_language", "en-US") or "en-US"
    messages = [
        {"role": "system", "content": build_system_prompt(name, is_sleeping, language)},
        {
            "role": "user",
            "content": (
                f"I want to teach you something.\n"
                f"Topic: {topic}\n"
                f"Content: {content}"
            ),
        },
    ]
    client = get_llm_client()
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
