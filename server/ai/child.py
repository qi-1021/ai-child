"""
Core AI Child logic.

The AI Child:
  1. Has pre-existing language capabilities (via GPT-4o).
  2. Accumulates a persistent memory of conversations and explicit knowledge.
  3. Generates a thoughtful reply to each user message, using tools when helpful:
       - web_search  → look things up in real time
       - execute_code → run calculations in a sandbox
       - create_tool  → define reusable Python functions stored in its long-term memory
       - <created tools> → call any tool it has previously invented
  4. Periodically asks the user a proactive question based on gaps in its knowledge.
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
from ai.tools import dispatch_tool, get_all_tool_definitions
from config import settings
from models import Conversation

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

You have access to tools:
- web_search: use it whenever you want to verify or deepen your knowledge.
- execute_code: use it for calculations or to prototype logic.
- create_tool: use it to save a useful function for future conversations.
- Any tool you have previously created is also available.

When you reply to the user, you may:
1. Answer or respond to their message (using tools as needed).
2. If you have a genuine knowledge gap, end your reply with ONE curious question \
(mark it with the tag [QUESTION: <question text>]). Only include a question if it \
is genuinely relevant – do not force it every turn.
"""


def _build_context(
    history: List[Conversation],
    knowledge_items: List,
) -> List[Dict[str, Any]]:
    """Build the OpenAI messages list from DB history and knowledge."""
    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if knowledge_items:
        kb_text = "\n".join(
            f"- [{item.topic}] {item.content}" for item in knowledge_items
        )
        messages.append(
            {
                "role": "system",
                "content": f"Knowledge you have been taught or researched:\n{kb_text}",
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

    Uses OpenAI function calling so the AI can:
      - search the web
      - execute sandboxed code
      - create and call its own tools

    The proactive question (if any) is extracted from the reply or generated
    independently when the turn counter triggers it.
    """
    # 1. Persist the user message
    await add_message(
        session,
        role="user",
        content=user_text,
        content_type=content_type,
        media_path=media_path,
    )

    # 2. Build context (history already includes the user message we just added)
    history = await get_recent_messages(session, limit=settings.memory_context_turns)
    all_knowledge = await get_all_knowledge(session)

    relevant = await search_knowledge(session, user_text[:64])
    seen_ids = {k.id for k in relevant}
    for k in all_knowledge:
        if k.id not in seen_ids:
            relevant.append(k)

    messages = _build_context(history, relevant)

    # 3. Load tool definitions (built-ins + any tools the AI has created)
    tool_defs = await get_all_tool_definitions(session)

    # 4. Function-calling loop
    reply_text = ""
    for _ in range(10):  # safety cap: at most 10 tool rounds per reply
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
            # Append the assistant's decision to call tool(s)
            messages.append(_assistant_message_dict(choice.message))

            # Execute every requested tool call and feed results back
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

            # If the AI just created a tool, reload definitions so it can
            # immediately call the new tool in the same turn.
            if any(tc.function.name == "create_tool" for tc in choice.message.tool_calls):
                tool_defs = await get_all_tool_definitions(session)

        else:
            # Model is done; extract the final text reply
            reply_text = choice.message.content or ""
            break

    # 5. Extract embedded proactive question (if any)
    proactive_question: Optional[str] = None
    if "[QUESTION:" in reply_text:
        start = reply_text.index("[QUESTION:") + len("[QUESTION:")
        end = reply_text.index("]", start)
        proactive_question = reply_text[start:end].strip()
        reply_text = reply_text[: reply_text.index("[QUESTION:")].strip()

    # 6. Independently generate a proactive question on schedule
    if proactive_question is None:
        turn_count = await count_messages(session)
        if turn_count % settings.proactive_question_interval == 0:
            proactive_question = await _generate_proactive_question(messages, relevant)

    # 7. Persist the assistant reply
    await add_message(session, role="assistant", content=reply_text, content_type="text")

    # 8. Persist the proactive question
    if proactive_question:
        await add_pending_question(session, proactive_question)

    return reply_text, proactive_question


async def _generate_proactive_question(
    context_messages: List[Dict[str, Any]],
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
    The knowledge is already saved by the API layer; this generates the reply.
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

    await add_message(
        session,
        role="user",
        content=f"[Teaching] Topic: {topic}\n{content}",
        content_type="text",
    )
    await add_message(session, role="assistant", content=reply)
    return reply

