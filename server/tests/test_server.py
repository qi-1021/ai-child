"""
Unit and integration tests for the AI Child server.

These tests use a temporary in-memory SQLite database and mock the OpenAI
client so they run without any network access or API key.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True, scope="session")
def patch_settings(tmp_path_factory):
    """Override the database URL and OpenAI key before importing the app."""
    tmp = tmp_path_factory.mktemp("db")
    db_path = tmp / "test.db"
    with patch.dict(
        "os.environ",
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
            "OPENAI_API_KEY": "sk-test",
        },
    ):
        yield


@pytest.fixture(scope="session")
async def app(patch_settings):
    import sys

    # Reload modules so they pick up patched env vars
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith(("config", "models", "ai.", "api.", "main")):
            sys.modules.pop(mod_name, None)

    from main import app as fastapi_app
    from models import init_db

    await init_db()
    return fastapi_app


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Health endpoints ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "AI Child"
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── Chat history ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_history_empty(client):
    response = await client.get("/chat/history")
    assert response.status_code == 200
    body = response.json()
    assert "messages" in body
    assert isinstance(body["messages"], list)


# ── Text chat ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_text_message(client):
    mock_choice = MagicMock()
    mock_choice.message.content = "Hello! Nice to meet you."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_llm = MagicMock()
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)
    with patch("ai.child.get_llm_client", return_value=mock_llm):
        response = await client.post(
            "/chat/text", data={"text": "Hello, who are you?"}
        )

    assert response.status_code == 200
    body = response.json()
    assert "reply" in body
    assert body["reply"] == "Hello! Nice to meet you."
    assert "proactive_question" in body


@pytest.mark.asyncio
async def test_send_text_with_embedded_question(client):
    """Reply that embeds a [QUESTION: ...] tag should be split correctly."""
    mock_choice = MagicMock()
    mock_choice.message.content = (
        "That is interesting! [QUESTION: What is your favourite colour?]"
    )
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_llm = MagicMock()
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)
    with patch("ai.child.get_llm_client", return_value=mock_llm):
        response = await client.post(
            "/chat/text", data={"text": "I love painting."}
        )

    assert response.status_code == 200
    body = response.json()
    assert "[QUESTION:" not in body["reply"]
    assert body["proactive_question"] == "What is your favourite colour?"


# ── Teaching ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_teach_knowledge(client):
    mock_choice = MagicMock()
    mock_choice.message.content = "Oh, I did not know that! Thank you for telling me."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_llm = MagicMock()
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)
    with patch("ai.child.get_llm_client", return_value=mock_llm):
        response = await client.post(
            "/teach/",
            json={"topic": "gravity", "content": "Objects fall at 9.8 m/s² on Earth."},
        )

    assert response.status_code == 200
    body = response.json()
    assert "reply" in body


@pytest.mark.asyncio
async def test_list_knowledge(client):
    response = await client.get("/teach/knowledge")
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    topics = [i["topic"] for i in items]
    assert "gravity" in topics


# ── Questions ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_questions(client):
    response = await client.get("/teach/questions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_answer_nonexistent_question(client):
    response = await client.post(
        "/teach/questions/99999/answer", json={"answer": "Because it is."}
    )
    assert response.status_code == 404


# ── Memory helpers ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_add_and_retrieve():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from models import Base
    from ai.memory import add_message, get_recent_messages, count_messages

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        await add_message(session, role="user", content="Hello")
        await add_message(session, role="assistant", content="Hi there!")
        msgs = await get_recent_messages(session, limit=10)
        assert len(msgs) == 2
        assert msgs[0].content == "Hello"
        assert msgs[1].content == "Hi there!"
        total = await count_messages(session)
        assert total == 2
