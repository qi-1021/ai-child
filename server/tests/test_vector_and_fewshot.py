"""
Tests for vector-based semantic memory (ai/vector_store.py) and
few-shot self-teaching engine (ai/few_shot.py).
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models import KnowledgeItem


# ── vector_store: _cosine_similarity ─────────────────────────────────────────

def test_cosine_similarity_identical():
    from ai.vector_store import _cosine_similarity
    v = [1.0, 0.0, 0.0]
    assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    from ai.vector_store import _cosine_similarity
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(_cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_zero_vector():
    from ai.vector_store import _cosine_similarity
    a = [0.0, 0.0]
    b = [1.0, 0.0]
    assert _cosine_similarity(a, b) == 0.0


# ── vector_store: embed_text ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_embed_text_returns_embedding():
    fake_embedding = [0.1, 0.2, 0.3]
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_embedding)]
    mock_llm = MagicMock()
    mock_llm.embeddings.create = AsyncMock(return_value=mock_response)

    with patch("ai.vector_store.get_llm_client", return_value=mock_llm):
        from ai.vector_store import embed_text
        result = await embed_text("hello world")

    assert result == fake_embedding


@pytest.mark.asyncio
async def test_embed_text_returns_none_on_error():
    mock_llm = MagicMock()
    mock_llm.embeddings.create = AsyncMock(side_effect=Exception("API error"))

    with patch("ai.vector_store.get_llm_client", return_value=mock_llm):
        from ai.vector_store import embed_text
        result = await embed_text("hello world")

    assert result is None


# ── vector_store: store_embedding ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_store_embedding_persists(session):
    fake_embedding = [0.1, 0.2, 0.3]
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=fake_embedding)]
    mock_llm = MagicMock()
    mock_llm.embeddings.create = AsyncMock(return_value=mock_response)

    item = KnowledgeItem(topic="gravity", content="Objects fall at 9.8 m/s²")
    session.add(item)
    await session.commit()

    with patch("ai.vector_store.get_llm_client", return_value=mock_llm):
        from ai.vector_store import store_embedding
        success = await store_embedding(session, item)

    assert success is True
    assert item.embedding is not None
    stored = json.loads(item.embedding)
    assert stored == fake_embedding


@pytest.mark.asyncio
async def test_store_embedding_returns_false_on_error(session):
    mock_llm = MagicMock()
    mock_llm.embeddings.create = AsyncMock(side_effect=Exception("no key"))

    item = KnowledgeItem(topic="test", content="some content")
    session.add(item)
    await session.commit()

    with patch("ai.vector_store.get_llm_client", return_value=mock_llm):
        from ai.vector_store import store_embedding
        success = await store_embedding(session, item)

    assert success is False
    assert item.embedding is None


# ── vector_store: search_semantic ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_semantic_returns_top_k(session):
    """Items with stored embeddings are ranked by cosine similarity."""
    emb_a = [1.0, 0.0, 0.0]
    emb_b = [0.0, 1.0, 0.0]
    emb_c = [0.9, 0.1, 0.0]   # closest to emb_a

    item_a = KnowledgeItem(topic="alpha", content="aaa", embedding=json.dumps(emb_a))
    item_b = KnowledgeItem(topic="beta", content="bbb", embedding=json.dumps(emb_b))
    item_c = KnowledgeItem(topic="gamma", content="ccc", embedding=json.dumps(emb_c))
    session.add_all([item_a, item_b, item_c])
    await session.commit()

    # Query embedding similar to emb_a/emb_c
    query_emb = [0.95, 0.05, 0.0]
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=query_emb)]
    mock_llm = MagicMock()
    mock_llm.embeddings.create = AsyncMock(return_value=mock_response)

    with patch("ai.vector_store.get_llm_client", return_value=mock_llm):
        from ai.vector_store import search_semantic
        results = await search_semantic(session, "query", top_k=2, min_similarity=0.0)

    assert len(results) == 2
    topics = [item.topic for item, _ in results]
    # alpha and gamma should rank above beta
    assert "beta" not in topics


@pytest.mark.asyncio
async def test_search_semantic_falls_back_when_no_embeddings(session):
    """When no items have embeddings, returns empty list."""
    item = KnowledgeItem(topic="noembed", content="no embedding stored")
    session.add(item)
    await session.commit()

    query_emb = [0.5, 0.5]
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=query_emb)]
    mock_llm = MagicMock()
    mock_llm.embeddings.create = AsyncMock(return_value=mock_response)

    with patch("ai.vector_store.get_llm_client", return_value=mock_llm):
        from ai.vector_store import search_semantic
        results = await search_semantic(session, "query")

    assert results == []


@pytest.mark.asyncio
async def test_search_semantic_returns_empty_when_embed_fails(session):
    """Graceful degradation: returns [] when embed_text returns None."""
    item = KnowledgeItem(topic="t", content="c", embedding=json.dumps([1.0, 0.0]))
    session.add(item)
    await session.commit()

    mock_llm = MagicMock()
    mock_llm.embeddings.create = AsyncMock(side_effect=Exception("no key"))

    with patch("ai.vector_store.get_llm_client", return_value=mock_llm):
        from ai.vector_store import search_semantic
        results = await search_semantic(session, "query")

    assert results == []


# ── memory: search_knowledge uses semantic then falls back ────────────────────

@pytest.mark.asyncio
async def test_memory_search_uses_ilike_fallback(session):
    """When semantic search returns nothing, ILIKE fallback works."""
    from models import KnowledgeItem as KI
    item = KI(topic="Python language", content="A high-level programming language")
    session.add(item)
    await session.commit()

    # Embedding fails → semantic search returns [] → ILIKE kicks in
    mock_llm = MagicMock()
    mock_llm.embeddings.create = AsyncMock(side_effect=Exception("no key"))

    with patch("ai.vector_store.get_llm_client", return_value=mock_llm):
        from ai.memory import search_knowledge
        results = await search_knowledge(session, "Python")

    assert len(results) >= 1
    assert any("Python" in r.topic for r in results)


# ── few_shot: generate_inferences stores self-knowledge ──────────────────────

@pytest.mark.asyncio
async def test_generate_inferences_stores_items():
    """generate_inferences should store low-confidence self-knowledge items."""
    mock_choice = MagicMock()
    mock_choice.message.content = '["Apples are fruit.", "Fruit grows on trees."]'
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    mock_llm = MagicMock()
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_resp)
    # Embedding will fail gracefully in test (no embed key)
    mock_llm.embeddings.create = AsyncMock(side_effect=Exception("no key"))

    stored_items = []

    async def fake_add_knowledge(session, topic, content, source, confidence):
        item = KnowledgeItem(
            topic=topic, content=content, source=source, confidence=confidence
        )
        stored_items.append(item)
        return item

    with (
        patch("ai.few_shot.get_llm_client", return_value=mock_llm),
        patch("ai.few_shot.get_active_model", return_value="gpt-4o"),
        patch("ai.few_shot.settings") as mock_settings,
        patch("ai.few_shot.async_session") as mock_session_ctx,
        patch("ai.few_shot.add_knowledge", new=AsyncMock(side_effect=fake_add_knowledge)),
        patch("ai.few_shot.store_embedding", new=AsyncMock(return_value=False)),
    ):
        mock_settings.few_shot_enabled = True
        mock_settings.few_shot_inference_count = 2
        mock_settings.few_shot_confidence = 50

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx.return_value = mock_session

        from ai.few_shot import generate_inferences
        await generate_inferences("Apple", "Apples are red fruits.")

    assert len(stored_items) == 2
    for item in stored_items:
        assert item.source == "self"
        assert item.confidence == 50


@pytest.mark.asyncio
async def test_generate_inferences_skipped_when_disabled():
    """When few_shot_enabled=False nothing should be called."""
    with patch("ai.few_shot.settings") as mock_settings:
        mock_settings.few_shot_enabled = False
        mock_llm = MagicMock()
        with patch("ai.few_shot.get_llm_client", return_value=mock_llm):
            from ai.few_shot import generate_inferences
            await generate_inferences("topic", "content")
    mock_llm.chat.completions.create.assert_not_called()


# ── i18n: build_system_prompt ─────────────────────────────────────────────────

def test_build_system_prompt_unnamed_english():
    from i18n.messages import build_system_prompt
    prompt = build_system_prompt(name=None, language="en-US")
    assert "don't have a name" in prompt
    assert "web_search" in prompt


def test_build_system_prompt_named_chinese():
    from i18n.messages import build_system_prompt
    prompt = build_system_prompt(name="小智", language="zh-CN")
    assert "小智" in prompt
    assert "web_search" in prompt


def test_build_system_prompt_sleeping_note_english():
    from i18n.messages import build_system_prompt
    prompt = build_system_prompt(name="Buddy", is_sleeping=True, language="en-US")
    assert "sleep" in prompt.lower() or "rest" in prompt.lower()


def test_build_system_prompt_sleeping_note_chinese():
    from i18n.messages import build_system_prompt
    prompt = build_system_prompt(name="小智", is_sleeping=True, language="zh-CN")
    assert "休眠" in prompt or "休息" in prompt


def test_build_system_prompt_falls_back_to_english_for_unknown_lang():
    from i18n.messages import build_system_prompt
    prompt = build_system_prompt(name=None, language="fr-FR")
    assert "web_search" in prompt


# ── i18n: name_accepted key ───────────────────────────────────────────────────

def test_name_accepted_english():
    from i18n import t
    msg = t("name_accepted", language="en-US", ai_name="Buddy")
    assert "Buddy" in msg


def test_name_accepted_chinese():
    from i18n import t
    msg = t("name_accepted", language="zh-CN", ai_name="小智")
    assert "小智" in msg
