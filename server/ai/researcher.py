"""
Autonomous research engine.

After the user answers one of the AI's questions, the researcher:
  1. Generates targeted web-search queries based on the topic + answer.
  2. Searches DuckDuckGo for each query.
  3. Uses GPT-4o to summarise the findings into concise knowledge.
  4. Stores the summary as a self-sourced KnowledgeItem (confidence 70).

This runs as a background asyncio task so the API response is never delayed.
"""
import json
import logging
from typing import List

from openai import AsyncOpenAI

from ai.llm_provider import get_llm_client, get_active_model
from ai.memory import add_knowledge
from ai.tools import format_search_results, web_search
from config import settings
from models import async_session

logger = logging.getLogger(__name__)


async def _generate_search_queries(topic: str, seed_answer: str) -> List[str]:
    """Ask GPT-4o to generate search queries that deepen knowledge on a topic."""
    prompt = (
        f"I just learned that regarding '{topic}': {seed_answer}\n\n"
        f"Give me {settings.research_query_count} short, specific web-search queries "
        f"to understand this topic more deeply. "
        f"Return them as a JSON array of strings with no extra text."
    )
    try:
        client = get_llm_client()
        response = await client.chat.completions.create(
            model=get_active_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.7,
        )
        raw = (response.choices[0].message.content or "").strip()
        queries = json.loads(raw)
        if isinstance(queries, list):
            return [str(q) for q in queries[: settings.research_query_count]]
    except Exception as exc:
        logger.warning("Failed to generate search queries for '%s': %s", topic, exc)
    # Fallback: single query constructed from topic + first 40 chars of answer
    return [f"{topic} {seed_answer[:40]}"]


async def _summarise_findings(topic: str, seed_answer: str, search_text: str) -> str:
    """Summarise raw search snippets into concise self-knowledge."""
    prompt = (
        f"I am an AI learning about '{topic}'.\n"
        f"I was told: {seed_answer}\n\n"
        f"I searched the internet and found:\n{search_text}\n\n"
        f"Summarise the most important verifiable facts in 3–5 sentences. "
        f"Do not include URLs. Write in third person."
    )
    try:
        client = get_llm_client()
        response = await client.chat.completions.create(
            model=get_active_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.3,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("Failed to summarise research findings: %s", exc)
        return ""


async def research_topic(topic: str, seed_answer: str) -> None:
    """
    Background task: search the web on a topic and store self-learned knowledge.

    Opens its own DB session because the originating HTTP request session
    will have been closed by the time this coroutine runs.
    """
    if not settings.research_enabled:
        return

    logger.info("Autonomous research started: topic='%s'", topic)
    async with async_session() as session:
        try:
            queries = await _generate_search_queries(topic, seed_answer)
            logger.info("Research queries: %s", queries)

            all_results = []
            for query in queries:
                results = await web_search(
                    query, max_results=settings.research_max_results
                )
                all_results.extend(results)

            if not all_results:
                logger.info("No search results returned for topic '%s'", topic)
                return

            search_text = format_search_results(all_results[:10])
            summary = await _summarise_findings(topic, seed_answer, search_text)

            if summary:
                await add_knowledge(
                    session,
                    topic=topic,
                    content=summary,
                    source="self",
                    confidence=70,
                )
                logger.info(
                    "Self-researched knowledge stored for topic '%s'", topic
                )
        except Exception as exc:
            logger.exception(
                "Autonomous research failed for topic '%s': %s", topic, exc
            )
