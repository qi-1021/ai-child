"""
Tests for the bot bridge layer.

These tests mock the AI Child server HTTP calls so they run without a live
server or API key.
"""
import pytest
import respx
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


# ── ServerClient tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_server_client_send_text():
    from adapters.server_client import ServerClient

    with respx.mock(base_url="http://localhost:8000") as mock:
        mock.post("/chat/text").mock(
            return_value=httpx.Response(
                200,
                json={"reply": "Hello!", "proactive_question": None},
            )
        )
        async with ServerClient("http://localhost:8000") as srv:
            reply, question = await srv.send_text("Hi there")

    assert reply == "Hello!"
    assert question is None


@pytest.mark.asyncio
async def test_server_client_teach():
    from adapters.server_client import ServerClient

    with respx.mock(base_url="http://localhost:8000") as mock:
        mock.post("/teach/").mock(
            return_value=httpx.Response(200, json={"reply": "Got it!"})
        )
        async with ServerClient("http://localhost:8000") as srv:
            reply = await srv.teach("gravity", "9.8 m/s²")

    assert reply == "Got it!"


@pytest.mark.asyncio
async def test_server_client_get_questions():
    from adapters.server_client import ServerClient

    questions = [{"id": 1, "question": "What is your name?", "topic": None, "answered": False, "created_at": "2024-01-01T00:00:00"}]
    with respx.mock(base_url="http://localhost:8000") as mock:
        mock.get("/teach/questions").mock(
            return_value=httpx.Response(200, json=questions)
        )
        async with ServerClient("http://localhost:8000") as srv:
            result = await srv.get_unanswered_questions()

    assert len(result) == 1
    assert result[0]["question"] == "What is your name?"


@pytest.mark.asyncio
async def test_server_client_answer_question():
    from adapters.server_client import ServerClient

    with respx.mock(base_url="http://localhost:8000") as mock:
        mock.post("/teach/questions/1/answer").mock(
            return_value=httpx.Response(200, json={"reply": "Thank you!"})
        )
        async with ServerClient("http://localhost:8000") as srv:
            reply = await srv.answer_question(1, "My name is Alice")

    assert reply == "Thank you!"


@pytest.mark.asyncio
async def test_server_client_send_image():
    from adapters.server_client import ServerClient

    with respx.mock(base_url="http://localhost:8000") as mock:
        mock.post("/chat/image").mock(
            return_value=httpx.Response(
                200,
                json={
                    "reply": "Nice photo!",
                    "proactive_question": "Where was this taken?",
                    "image_description": "A sunny beach",
                },
            )
        )
        async with ServerClient("http://localhost:8000") as srv:
            reply, question = await srv.send_image(b"fake_image", "test.jpg", "Vacation")

    assert reply == "Nice photo!"
    assert question == "Where was this taken?"


@pytest.mark.asyncio
async def test_server_client_send_audio():
    from adapters.server_client import ServerClient

    with respx.mock(base_url="http://localhost:8000") as mock:
        mock.post("/chat/audio").mock(
            return_value=httpx.Response(
                200,
                json={
                    "reply": "I heard you say hello!",
                    "proactive_question": None,
                    "transcription": "hello",
                },
            )
        )
        async with ServerClient("http://localhost:8000") as srv:
            reply, question = await srv.send_audio(b"fake_audio", "voice.ogg")

    assert reply == "I heard you say hello!"
    assert question is None


# ── Webhook adapter tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_text_message():
    from adapters.webhook import webhook_app
    from httpx import AsyncClient, ASGITransport

    with respx.mock(base_url="http://localhost:8000") as mock:
        mock.post("/chat/text").mock(
            return_value=httpx.Response(
                200, json={"reply": "Hello from bot!", "proactive_question": None}
            )
        )
        async with AsyncClient(
            transport=ASGITransport(app=webhook_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook/message",
                json={"chat_id": "123", "type": "text", "content": "Hello"},
            )

    assert response.status_code == 200
    assert response.json()["reply"] == "Hello from bot!"


@pytest.mark.asyncio
async def test_webhook_invalid_type():
    from adapters.webhook import webhook_app
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=webhook_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/webhook/message",
            json={"chat_id": "123", "type": "video", "content": "some content"},
        )

    assert response.status_code == 400


def test_webhook_secret_rejected():
    """_verify_secret raises HTTP 403 when the secret does not match."""
    from adapters import webhook as wh_module
    from fastapi import HTTPException

    original = wh_module.settings.webhook_secret
    try:
        wh_module.settings.webhook_secret = "correct-secret"
        with pytest.raises(HTTPException) as exc_info:
            wh_module._verify_secret("wrong-secret")
        assert exc_info.value.status_code == 403
    finally:
        wh_module.settings.webhook_secret = original


@pytest.mark.asyncio
async def test_webhook_health():
    from adapters.webhook import webhook_app
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=webhook_app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_webhook_get_questions():
    from adapters.webhook import webhook_app
    from httpx import AsyncClient, ASGITransport

    questions = [{"id": 2, "question": "What do you like?", "topic": None, "answered": False, "created_at": "2024-01-01T00:00:00"}]
    with respx.mock(base_url="http://localhost:8000") as mock:
        mock.get("/teach/questions").mock(
            return_value=httpx.Response(200, json=questions)
        )
        async with AsyncClient(
            transport=ASGITransport(app=webhook_app), base_url="http://test"
        ) as client:
            response = await client.get("/webhook/questions")

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_webhook_teach():
    from adapters.webhook import webhook_app
    from httpx import AsyncClient, ASGITransport

    with respx.mock(base_url="http://localhost:8000") as mock:
        mock.post("/teach/").mock(
            return_value=httpx.Response(200, json={"reply": "Learned!"})
        )
        async with AsyncClient(
            transport=ASGITransport(app=webhook_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook/teach",
                json={"topic": "history", "content": "World War II ended in 1945"},
            )

    assert response.status_code == 200
    assert response.json()["reply"] == "Learned!"
