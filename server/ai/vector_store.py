"""
Vector-based semantic memory using OpenAI-compatible embeddings + cosine similarity.

Each KnowledgeItem stores its embedding as a JSON-encoded float array in the
`embedding` TEXT column.  Semantic search works entirely in Python with numpy,
so no extra database extension is needed.

Graceful degradation: if the embedding API call fails (e.g. no key configured),
every function returns a safe default so the rest of the system keeps working.
"""

import json
import logging
from typing import List, Optional, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm_provider import get_llm_client
from config import settings
from models import KnowledgeItem

logger = logging.getLogger(__name__)


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Return the cosine similarity between two embedding vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = float(np.linalg.norm(va))
    norm_b = float(np.linalg.norm(vb))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


async def embed_text(text: str) -> Optional[List[float]]:
    """
    Generate an embedding for *text* using the configured embedding model.

    Returns the embedding vector on success, or None on failure (e.g. network
    error, missing API key).  Callers should treat None as "no embedding
    available" and fall back to keyword search.
    """
    try:
        client = get_llm_client()
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=text[:8000],  # stay within most model context windows
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.warning("Embedding failed (%s). Falling back to keyword search.", exc)
        return None


# ── Public API ────────────────────────────────────────────────────────────────

async def store_embedding(session: AsyncSession, item: KnowledgeItem) -> bool:
    """
    Compute and persist the embedding for a single KnowledgeItem.

    The embedding text is ``"<topic>: <content>"`` so both fields contribute
    to the vector representation.

    Returns True on success, False when embedding was unavailable.
    """
    text = f"{item.topic}: {item.content}"
    embedding = await embed_text(text)
    if embedding is None:
        return False
    item.embedding = json.dumps(embedding)
    await session.commit()
    return True


async def search_semantic(
    session: AsyncSession,
    query: str,
    top_k: int = 10,
    min_similarity: float = 0.0,
) -> List[Tuple[KnowledgeItem, float]]:
    """
    Semantic knowledge search using cosine similarity.

    Steps:
      1. Embed the query string.
      2. Load all KnowledgeItems that have a stored embedding.
      3. Compute cosine similarity between the query vector and each item.
      4. Return the top-k items above ``min_similarity``, sorted descending.

    Returns an empty list when the embedding API is unavailable or there are
    no embedded items yet — the caller should fall back to keyword search.
    """
    query_embedding = await embed_text(query)
    if query_embedding is None:
        return []

    result = await session.execute(
        select(KnowledgeItem).where(KnowledgeItem.embedding.isnot(None))
    )
    items = result.scalars().all()
    if not items:
        return []

    scored: List[Tuple[KnowledgeItem, float]] = []
    for item in items:
        try:
            item_vec = json.loads(item.embedding)
            sim = _cosine_similarity(query_embedding, item_vec)
            if sim >= min_similarity:
                scored.append((item, sim))
        except Exception:
            continue

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
