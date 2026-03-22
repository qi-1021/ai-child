"""
Dream phase — sleep-time model strengthening.

When the AI child goes to sleep it not only consolidates memories (ai/sleep.py)
but also *strengthens* the underlying model by:

  1. **Training-data export (universal)**
     High-confidence knowledge items are written as an OpenAI-compatible
     fine-tuning JSONL file.  The file can be used with:
       - OpenAI fine-tuning API   (cloud)
       - Axolotl / LLaMA-Factory  (local GPU fine-tuning)
       - llama.cpp LoRA trainer   (CPU fine-tuning)

  2. **Ollama model generation (local-only, opt-in)**
     When ``llm_provider = "ollama"`` and ``sleep_create_ollama_generation = True``,
     the dream module bakes the current high-confidence knowledge into an Ollama
     Modelfile and creates a new named model generation (e.g., ``aichild-gen1``).
     The new model is activated immediately without a server restart — all
     subsequent LLM calls use the strengthened model.

     This implements the vision of "将每天的知识转化为更牢靠的大模型":
     the child's knowledge gradually becomes encoded in the model's own weights
     (system prompt context) rather than only in the external knowledge base.

Why Modelfile, not gradient-based fine-tuning?
  Pure fine-tuning requires GPU hours and megabytes of training data.  A child
  learns from a few examples in seconds.  The Modelfile approach achieves the
  same qualitative goal — making the model "remember" its lessons across cold
  reboots — through knowledge-enriched system-prompt injection, which is fast,
  deterministic, and requires zero GPU.  When a GPU is available and enough
  training data has accumulated, the exported JSONL can be used for proper LoRA
  fine-tuning off-line.
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.llm_provider import get_active_model, set_active_model
from ai.profile import get_ai_name, get_or_create_profile
from config import settings
from i18n.messages import build_system_prompt
from models import KnowledgeItem, async_session

logger = logging.getLogger(__name__)


# ── Training-data export ──────────────────────────────────────────────────────

async def export_training_dataset(session: AsyncSession) -> Optional[str]:
    """
    Write today's high-confidence knowledge as an OpenAI-format fine-tuning
    JSONL file and return the file path.

    Each line is a training example:
    ::

        {"messages": [
            {"role": "system",    "content": "<system prompt>"},
            {"role": "user",      "content": "Tell me about <topic>"},
            {"role": "assistant", "content": "<knowledge content>"}
        ]}

    Returns the file path on success, or None if there is nothing to export.
    """
    if not settings.sleep_export_training_data:
        return None

    result = await session.execute(
        select(KnowledgeItem)
        .where(KnowledgeItem.confidence >= 70)
        .where(KnowledgeItem.source != "consolidation")  # avoid meta-items
        .order_by(KnowledgeItem.confidence.desc())
        .limit(500)
    )
    items = result.scalars().all()
    if not items:
        logger.info("Dream: no high-confidence knowledge to export.")
        return None

    name = await get_ai_name(session)
    profile = await get_or_create_profile(session)
    language = getattr(profile, "preferred_language", "en-US") or "en-US"
    system_prompt = build_system_prompt(name, is_sleeping=False, language=language)

    data_dir = Path(settings.training_data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = data_dir / f"training-{today}.jsonl"

    count = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for item in items:
            example = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"Tell me about: {item.topic}",
                    },
                    {
                        "role": "assistant",
                        "content": item.content,
                    },
                ]
            }
            fh.write(json.dumps(example, ensure_ascii=False) + "\n")
            count += 1

    logger.info("Dream: exported %d training examples → %s", count, out_path)
    return str(out_path)


# ── Ollama model generation ───────────────────────────────────────────────────

def _build_modelfile(
    base_model: str,
    system_prompt: str,
) -> str:
    """
    Build an Ollama Modelfile that derives from *base_model* and injects
    *system_prompt* (which already contains the consolidated knowledge) as the
    model's default SYSTEM instruction.
    """
    # Escape triple-quotes inside the prompt to avoid breaking the Modelfile
    safe_prompt = system_prompt.replace('"""', "'''")
    return (
        f'FROM {base_model}\n\n'
        f'SYSTEM """\n{safe_prompt}\n"""\n\n'
        f"PARAMETER temperature 0.7\n"
        f"PARAMETER top_p 0.9\n"
    )


def _run_ollama_create(model_name: str, modelfile_path: str) -> bool:
    """
    Run ``ollama create <model_name> -f <modelfile_path>`` synchronously.

    Returns True on success, False on failure.
    Runs in a subprocess so it doesn't block the asyncio event loop when
    called from ``asyncio.to_thread()``.
    """
    try:
        result = subprocess.run(
            ["ollama", "create", model_name, "-f", modelfile_path],
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute safety cap
        )
        if result.returncode == 0:
            logger.info("Dream: ollama model '%s' created successfully.", model_name)
            return True
        logger.warning(
            "Dream: ollama create failed (rc=%d): %s",
            result.returncode,
            result.stderr[:500],
        )
        return False
    except FileNotFoundError:
        logger.warning(
            "Dream: 'ollama' executable not found — skipping model generation. "
            "Install Ollama from https://ollama.com"
        )
        return False
    except subprocess.TimeoutExpired:
        logger.warning("Dream: ollama create timed out after 5 minutes.")
        return False
    except Exception as exc:
        logger.warning("Dream: ollama create raised an unexpected error: %s", exc)
        return False


async def create_ollama_generation(session: AsyncSession) -> Optional[str]:
    """
    Bake today's consolidated knowledge into a new Ollama model generation.

    Steps:
      1. Load high-confidence knowledge items.
      2. Build an enriched system prompt that includes all of them.
      3. Write a Modelfile that derives from the current active model.
      4. Run ``ollama create <prefix>-gen<N>`` in a thread-pool executor.
      5. If successful, call ``set_active_model()`` so future LLM calls
         immediately use the new generation.

    Returns the new model name on success, or None if skipped / failed.
    """
    if not settings.sleep_create_ollama_generation:
        return None
    if settings.llm_provider.lower() != "ollama":
        logger.info(
            "Dream: ollama generation skipped (provider is '%s', not 'ollama').",
            settings.llm_provider,
        )
        return None

    result = await session.execute(
        select(KnowledgeItem)
        .where(KnowledgeItem.confidence >= 75)
        .order_by(KnowledgeItem.confidence.desc())
        .limit(200)
    )
    items = result.scalars().all()
    if not items:
        logger.info("Dream: no sufficiently confident knowledge — skipping model generation.")
        return None

    name = await get_ai_name(session)
    profile = await get_or_create_profile(session)
    language = getattr(profile, "preferred_language", "en-US") or "en-US"
    base_system = build_system_prompt(name, is_sleeping=False, language=language)

    # Append consolidated knowledge to system prompt
    kb_lines = "\n".join(
        f"- [{item.topic}] {item.content[:200]}" for item in items
    )
    knowledge_header = (
        "\n\n## Consolidated Knowledge (confidence ≥ 75)\n"
        "The following facts have been verified and consolidated during sleep:\n"
    )
    enriched_system = base_system + knowledge_header + kb_lines

    # Determine generation number
    current_gen: int = getattr(profile, "model_generation", 0) or 0
    next_gen = current_gen + 1
    new_model_name = f"{settings.ollama_generation_prefix}-gen{next_gen}"

    # The base model to derive from is the *current* active model so generations
    # stack on top of each other (each one inherits the previous prompt).
    base_model = get_active_model()

    modelfile_content = _build_modelfile(base_model, enriched_system)

    # Write Modelfile to a temporary file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".Modelfile", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(modelfile_content)
        modelfile_path = tmp.name

    try:
        success = await asyncio.to_thread(_run_ollama_create, new_model_name, modelfile_path)
    finally:
        try:
            os.unlink(modelfile_path)
        except OSError:
            pass

    if not success:
        return None

    # Persist the new generation number
    profile.model_generation = next_gen
    await session.commit()

    # Activate the new model immediately (no restart needed)
    set_active_model(new_model_name)
    logger.info(
        "Dream: model generation %d created and activated: %s",
        next_gen,
        new_model_name,
    )
    return new_model_name


# ── Orchestration ─────────────────────────────────────────────────────────────

async def run_dream_cycle() -> dict:
    """
    Run the full dream cycle after memory consolidation.

    Opens its own DB session so it can be called from a background task
    independently of the sleep scheduler's session.

    Returns a summary dict with paths / model name for logging.
    """
    summary = {"training_data_path": None, "new_model": None}
    async with async_session() as session:
        try:
            # 1. Export fine-tuning dataset (always, if enabled)
            path = await export_training_dataset(session)
            summary["training_data_path"] = path

            # 2. Create Ollama model generation (opt-in)
            new_model = await create_ollama_generation(session)
            summary["new_model"] = new_model
        except Exception as exc:
            logger.exception("Dream cycle error: %s", exc)
    return summary
