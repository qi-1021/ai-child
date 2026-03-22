"""
Tests for the AI Child profile system (ai/profile.py):
  - get_or_create_profile
  - get_ai_name / set_ai_name
  - ensure_name_question_exists
  - extract_name_from_answer
  - Naming question answer flow via the teach API
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import AIProfile, Base, PendingQuestion


# ── In-memory DB fixture ──────────────────────────────────────────────────────

@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s


# ── get_or_create_profile ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_or_create_profile_creates_on_first_call(session):
    from ai.profile import get_or_create_profile

    profile = await get_or_create_profile(session)
    assert profile.id == 1
    assert profile.name is None


@pytest.mark.asyncio
async def test_get_or_create_profile_idempotent(session):
    from ai.profile import get_or_create_profile

    p1 = await get_or_create_profile(session)
    p2 = await get_or_create_profile(session)
    assert p1.id == p2.id


# ── get_ai_name / set_ai_name ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_ai_name_returns_none_initially(session):
    from ai.profile import get_ai_name

    assert await get_ai_name(session) is None


@pytest.mark.asyncio
async def test_set_ai_name_persists(session):
    from ai.profile import get_ai_name, set_ai_name

    await set_ai_name(session, "小明")
    assert await get_ai_name(session) == "小明"


# ── ensure_name_question_exists ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_name_question_creates_question_when_unnamed(session):
    from sqlalchemy import select
    from ai.profile import ensure_name_question_exists, NAME_QUESTION_TOPIC

    await ensure_name_question_exists(session)

    result = await session.execute(
        select(PendingQuestion).where(PendingQuestion.topic == NAME_QUESTION_TOPIC)
    )
    q = result.scalar_one_or_none()
    assert q is not None
    assert q.answered is False


@pytest.mark.asyncio
async def test_ensure_name_question_idempotent(session):
    """Calling it twice should not create a second question."""
    from sqlalchemy import func, select
    from ai.profile import ensure_name_question_exists, NAME_QUESTION_TOPIC

    await ensure_name_question_exists(session)
    await ensure_name_question_exists(session)

    result = await session.execute(
        select(func.count()).select_from(PendingQuestion)
        .where(PendingQuestion.topic == NAME_QUESTION_TOPIC)
    )
    count = result.scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_ensure_name_question_skipped_when_already_named(session):
    """If the AI already has a name, no question should be created."""
    from sqlalchemy import func, select
    from ai.profile import (
        ensure_name_question_exists,
        set_ai_name,
        NAME_QUESTION_TOPIC,
    )

    await set_ai_name(session, "已命名")
    await ensure_name_question_exists(session)

    result = await session.execute(
        select(func.count()).select_from(PendingQuestion)
        .where(PendingQuestion.topic == NAME_QUESTION_TOPIC)
    )
    assert result.scalar() == 0


# ── extract_name_from_answer ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_name_from_answer_via_gpt():
    """GPT extraction returns the parsed name."""
    mock_choice = MagicMock()
    mock_choice.message.content = "小智"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    mock_llm = MagicMock()
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch("ai.profile.get_llm_client", return_value=mock_llm):
        from ai import profile as profile_module
        name = await profile_module.extract_name_from_answer("你就叫小智吧")
    assert name == "小智"


@pytest.mark.asyncio
async def test_extract_name_falls_back_on_gpt_error():
    """When GPT fails, the raw answer (trimmed) is used as the name."""
    mock_llm = MagicMock()
    mock_llm.chat.completions.create = AsyncMock(side_effect=Exception("API unavailable"))

    with patch("ai.profile.get_llm_client", return_value=mock_llm):
        from ai import profile as profile_module
        name = await profile_module.extract_name_from_answer("Alex")
    assert name == "Alex"


# ── /profile endpoint ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True, scope="module")
def patch_env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("profile_db")
    db_path = tmp / "test.db"
    with patch.dict(
        "os.environ",
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
            "OPENAI_API_KEY": "sk-test",
        },
    ):
        yield


@pytest.fixture(scope="module")
async def api_client(patch_env):
    import sys
    for mod in list(sys.modules):
        if mod.startswith(("config", "models", "ai.", "api.", "main")):
            sys.modules.pop(mod, None)

    from httpx import AsyncClient, ASGITransport
    from main import app
    from models import init_db
    from ai.profile import ensure_name_question_exists
    from models import async_session

    await init_db()
    async with async_session() as s:
        await ensure_name_question_exists(s)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_profile_endpoint_unnamed(api_client):
    response = await api_client.get("/profile")
    assert response.status_code == 200
    body = response.json()
    assert body["has_name"] is False
    assert body["name"] is None


@pytest.mark.asyncio
async def test_answer_naming_question_sets_name(api_client):
    """Answering the __name__ question should update /profile."""
    # Get the name question ID
    qs_resp = await api_client.get("/teach/questions")
    assert qs_resp.status_code == 200
    questions = qs_resp.json()
    name_qs = [q for q in questions if q["topic"] == "__name__"]
    assert name_qs, "Expected a naming question in pending questions"
    qid = name_qs[0]["id"]

    # Answer it
    ans_resp = await api_client.post(
        f"/teach/questions/{qid}/answer",
        json={"answer": "叫小宝吧"},
    )
    assert ans_resp.status_code == 200
    body = ans_resp.json()
    assert "reply" in body
    # The reply should mention the extracted name or confirm naming
    assert ans_resp.status_code == 200

    # Verify profile is now set
    profile_resp = await api_client.get("/profile")
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["has_name"] is True
    assert profile["name"] is not None
    assert len(profile["name"]) > 0
