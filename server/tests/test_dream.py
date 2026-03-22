"""
Tests for the dream-phase model-strengthening module (ai/dream.py).

Covers:
  - JSONL training-data export format and content
  - export skipped when no high-confidence knowledge exists
  - export skipped when sleep_export_training_data=False
  - Ollama Modelfile content is well-formed
  - _run_ollama_create returns True on success, False on failure
  - create_ollama_generation skips when provider != ollama
  - create_ollama_generation creates model and calls set_active_model on success
  - run_dream_cycle orchestrates both steps
  - get_active_model / set_active_model runtime switching
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import KnowledgeItem


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_item(topic: str, content: str, confidence: int = 90, source: str = "user"):
    return KnowledgeItem(
        topic=topic, content=content, confidence=confidence, source=source
    )


# ── get_active_model / set_active_model ───────────────────────────────────────

def test_get_active_model_default_openai():
    from ai.llm_provider import LLMProvider, get_active_model
    LLMProvider._active_model = None
    with patch("ai.llm_provider.settings") as s:
        s.llm_provider = "openai"
        s.openai_model = "gpt-4o"
        assert get_active_model() == "gpt-4o"


def test_get_active_model_default_ollama():
    from ai.llm_provider import LLMProvider, get_active_model
    LLMProvider._active_model = None
    with patch("ai.llm_provider.settings") as s:
        s.llm_provider = "ollama"
        s.ollama_model = "llama3.2"
        assert get_active_model() == "llama3.2"


def test_set_active_model_overrides():
    from ai.llm_provider import LLMProvider, get_active_model, set_active_model
    LLMProvider._active_model = None
    set_active_model("aichild-gen3")
    assert get_active_model() == "aichild-gen3"
    LLMProvider._active_model = None  # cleanup


def test_get_embedding_model_ollama():
    from ai.llm_provider import LLMProvider, get_embedding_model
    LLMProvider._active_model = None
    with patch("ai.llm_provider.settings") as s:
        s.llm_provider = "ollama"
        s.ollama_embedding_model = "nomic-embed-text"
        assert get_embedding_model() == "nomic-embed-text"


def test_get_embedding_model_openai():
    from ai.llm_provider import LLMProvider, get_embedding_model
    LLMProvider._active_model = None
    with patch("ai.llm_provider.settings") as s:
        s.llm_provider = "openai"
        s.embedding_model = "text-embedding-3-small"
        assert get_embedding_model() == "text-embedding-3-small"


# ── Ollama provider client creation ──────────────────────────────────────────

def test_llm_provider_creates_ollama_client():
    from ai.llm_provider import LLMProvider
    LLMProvider._instance = None
    with patch("ai.llm_provider.settings") as s:
        s.llm_provider = "ollama"
        s.ollama_base_url = "http://localhost:11434/v1"
        client = LLMProvider._create_client()
    assert client.base_url.host == "localhost"
    LLMProvider._instance = None  # cleanup


# ── _build_modelfile ──────────────────────────────────────────────────────────

def test_build_modelfile_structure():
    from ai.dream import _build_modelfile
    mf = _build_modelfile("llama3.2", "You are a curious AI child.")
    assert mf.startswith("FROM llama3.2")
    assert "SYSTEM" in mf
    assert "You are a curious AI child." in mf
    assert "PARAMETER temperature" in mf


def test_build_modelfile_escapes_triple_quotes():
    from ai.dream import _build_modelfile
    prompt_with_quotes = 'Say: """hello"""'
    mf = _build_modelfile("llama3.2", prompt_with_quotes)
    # Should not contain raw triple double-quotes inside the SYSTEM block
    # (they get replaced by triple single-quotes)
    assert '"""hello"""' not in mf


# ── _run_ollama_create ────────────────────────────────────────────────────────

def test_run_ollama_create_success():
    from ai.dream import _run_ollama_create
    with patch("ai.dream.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = _run_ollama_create("aichild-gen1", "/tmp/Modelfile")
    assert result is True
    mock_run.assert_called_once()


def test_run_ollama_create_nonzero_exit():
    from ai.dream import _run_ollama_create
    with patch("ai.dream.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="error msg")
        result = _run_ollama_create("aichild-gen1", "/tmp/Modelfile")
    assert result is False


def test_run_ollama_create_not_found():
    from ai.dream import _run_ollama_create
    with patch("ai.dream.subprocess.run", side_effect=FileNotFoundError):
        result = _run_ollama_create("aichild-gen1", "/tmp/Modelfile")
    assert result is False


# ── export_training_dataset ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_training_dataset_writes_jsonl(session, tmp_path):
    """Exported file is valid JSONL with correct message structure."""
    item = _make_item("cats", "Cats are feline mammals.", confidence=90)
    session.add(item)
    await session.commit()

    with (
        patch("ai.dream.settings") as mock_settings,
        patch("ai.dream.get_ai_name", new=AsyncMock(return_value="TestBot")),
        patch("ai.dream.get_or_create_profile", new=AsyncMock(return_value=MagicMock(preferred_language="en-US"))),
    ):
        mock_settings.sleep_export_training_data = True
        mock_settings.training_data_dir = str(tmp_path)

        from ai.dream import export_training_dataset
        path = await export_training_dataset(session)

    assert path is not None
    lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    example = json.loads(lines[0])
    assert "messages" in example
    roles = [m["role"] for m in example["messages"]]
    assert roles == ["system", "user", "assistant"]


@pytest.mark.asyncio
async def test_export_training_dataset_skips_when_disabled(session, tmp_path):
    with patch("ai.dream.settings") as mock_settings:
        mock_settings.sleep_export_training_data = False
        from ai.dream import export_training_dataset
        path = await export_training_dataset(session)
    assert path is None


@pytest.mark.asyncio
async def test_export_training_dataset_skips_when_no_items(session, tmp_path):
    """Returns None when no high-confidence items exist."""
    with (
        patch("ai.dream.settings") as mock_settings,
        patch("ai.dream.get_ai_name", new=AsyncMock(return_value=None)),
        patch("ai.dream.get_or_create_profile", new=AsyncMock(return_value=MagicMock(preferred_language="en-US"))),
    ):
        mock_settings.sleep_export_training_data = True
        mock_settings.training_data_dir = str(tmp_path)
        from ai.dream import export_training_dataset
        path = await export_training_dataset(session)
    assert path is None


# ── create_ollama_generation ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_ollama_generation_skipped_for_non_ollama(session):
    with patch("ai.dream.settings") as mock_settings:
        mock_settings.sleep_create_ollama_generation = True
        mock_settings.llm_provider = "openai"
        from ai.dream import create_ollama_generation
        result = await create_ollama_generation(session)
    assert result is None


@pytest.mark.asyncio
async def test_create_ollama_generation_skipped_when_disabled(session):
    with patch("ai.dream.settings") as mock_settings:
        mock_settings.sleep_create_ollama_generation = False
        mock_settings.llm_provider = "ollama"
        from ai.dream import create_ollama_generation
        result = await create_ollama_generation(session)
    assert result is None


@pytest.mark.asyncio
async def test_create_ollama_generation_success(session):
    """When ollama create succeeds, the new model name is returned and set as active."""
    item = _make_item("physics", "Objects fall at 9.8 m/s².", confidence=85)
    session.add(item)
    await session.commit()

    mock_profile = MagicMock()
    mock_profile.preferred_language = "en-US"
    mock_profile.model_generation = 0

    with (
        patch("ai.dream.settings") as mock_settings,
        patch("ai.dream.get_ai_name", new=AsyncMock(return_value="TestBot")),
        patch("ai.dream.get_or_create_profile", new=AsyncMock(return_value=mock_profile)),
        patch("ai.dream.get_active_model", return_value="llama3.2"),
        patch("ai.dream.set_active_model") as mock_set,
        patch("ai.dream._run_ollama_create", return_value=True),
        patch("ai.dream.asyncio.to_thread", new=AsyncMock(return_value=True)),
        patch("ai.dream.tempfile.NamedTemporaryFile") as mock_tmp,
        patch("ai.dream.os.unlink"),
    ):
        mock_settings.sleep_create_ollama_generation = True
        mock_settings.llm_provider = "ollama"
        mock_settings.ollama_generation_prefix = "aichild"

        # Make NamedTemporaryFile a context manager returning a file-like
        fake_file = MagicMock()
        fake_file.__enter__ = MagicMock(return_value=fake_file)
        fake_file.__exit__ = MagicMock(return_value=False)
        fake_file.name = "/tmp/test.Modelfile"
        mock_tmp.return_value = fake_file

        from ai.dream import create_ollama_generation
        result = await create_ollama_generation(session)

    assert result == "aichild-gen1"
    mock_set.assert_called_once_with("aichild-gen1")


@pytest.mark.asyncio
async def test_create_ollama_generation_skips_when_no_knowledge(session):
    """Returns None when no knowledge meets the confidence threshold."""
    with (
        patch("ai.dream.settings") as mock_settings,
        patch("ai.dream.get_ai_name", new=AsyncMock(return_value=None)),
        patch("ai.dream.get_or_create_profile", new=AsyncMock(return_value=MagicMock(preferred_language="en-US", model_generation=0))),
    ):
        mock_settings.sleep_create_ollama_generation = True
        mock_settings.llm_provider = "ollama"
        from ai.dream import create_ollama_generation
        result = await create_ollama_generation(session)
    assert result is None


# ── run_dream_cycle ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_dream_cycle_returns_summary():
    """run_dream_cycle returns a dict with both keys."""
    with (
        patch("ai.dream.export_training_dataset", new=AsyncMock(return_value="/tmp/train.jsonl")),
        patch("ai.dream.create_ollama_generation", new=AsyncMock(return_value=None)),
        patch("ai.dream.async_session") as mock_session_ctx,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        from ai.dream import run_dream_cycle
        result = await run_dream_cycle()

    assert result["training_data_path"] == "/tmp/train.jsonl"
    assert result["new_model"] is None
