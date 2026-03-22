"""
Few-shot self-teaching engine.

Human children generalise remarkably well from just a handful of examples —
they hear one or two sentences and immediately start making inferences,
forming analogies, and asking follow-up questions.

This module mimics that behaviour: whenever the AI Child is taught something
new it:

  1. Asks the LLM to generate ``few_shot_inference_count`` plausible
     inferences / generalisations that a curious child might derive from
     the single teaching example.
  2. Stores each inference as a KnowledgeItem with ``source="self"``
     and a configurable lower confidence (default 50), signalling that
     these are hypotheses to be validated, not verified facts.
  3. The inference generation runs as a *background* asyncio task so it
     never delays the HTTP response to the user.

The stored inferences feed back into the semantic search layer, so the AI
can reason from them in future conversations even before the user provides
more examples.
"""

import json
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm_provider import get_llm_client
from ai.memory import add_knowledge
from ai.vector_store import store_embedding
from config import settings
from models import KnowledgeItem, async_session

logger = logging.getLogger(__name__)


async def generate_inferences(
    topic: str,
    content: str,
) -> None:
    """
    Background task: derive few-shot inferences from a single teaching event
    and store them in the knowledge base as low-confidence self-knowledge.

    Opens its own DB session so the originating HTTP session can be closed.
    """
    if not settings.few_shot_enabled:
        return

    logger.info("Few-shot inference started for topic='%s'", topic)

    prompt = (
        f"You are a curious AI child who just learned one new fact:\n"
        f"Topic: {topic}\n"
        f"Fact: {content}\n\n"
        f"Like a child who generalises from just a few examples, list exactly "
        f"{settings.few_shot_inference_count} short, plausible inferences or "
        f"related things you might reasonably deduce from this single fact. "
        f"Each inference should be a complete sentence.\n\n"
        f"Return ONLY a JSON array of strings — no extra text:\n"
        f'["inference 1", "inference 2", ...]'
    )

    try:
        client = get_llm_client()
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.7,
        )
        raw = (response.choices[0].message.content or "").strip()

        # Strip markdown code fence if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        import json

        inferences = json.loads(raw)
        if not isinstance(inferences, list):
            raise ValueError("Expected a JSON array")
    except Exception as exc:
        logger.warning("Few-shot inference generation failed for '%s': %s", topic, exc)
        return

    async with async_session() as session:
        stored = 0
        for inference in inferences[: settings.few_shot_inference_count]:
            inference = str(inference).strip()
            if not inference:
                continue
            try:
                item = await add_knowledge(
                    session,
                    topic=topic,
                    content=inference,
                    source="self",
                    confidence=settings.few_shot_confidence,
                )
                # Embed in the same background task (no rush)
                await store_embedding(session, item)
                stored += 1
            except Exception as exc:
                logger.warning("Failed to store inference for '%s': %s", topic, exc)

        logger.info(
            "Few-shot: stored %d inference(s) for topic='%s'", stored, topic
        )
