"""
HTTP client helper for the AI Child server REST API.
"""
import logging
from typing import Optional, Tuple

import httpx

from config import settings

logger = logging.getLogger(__name__)


class ServerClient:
    """Thin async client that wraps the AI Child server REST API."""

    def __init__(self, base_url: str = ""):
        self._base = base_url or settings.server_url
        self._http: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._http = httpx.AsyncClient(base_url=self._base, timeout=30)
        return self

    async def __aexit__(self, *_):
        if self._http:
            await self._http.aclose()

    # ── Chat ──────────────────────────────────────────────────────────────

    async def send_text(self, text: str) -> Tuple[str, Optional[str]]:
        """POST /chat/text → (reply, proactive_question | None)."""
        r = await self._http.post("/chat/text", data={"text": text})
        r.raise_for_status()
        body = r.json()
        return body["reply"], body.get("proactive_question")

    async def send_image(
        self, image_bytes: bytes, filename: str, caption: str = ""
    ) -> Tuple[str, Optional[str]]:
        """POST /chat/image → (reply, proactive_question | None)."""
        r = await self._http.post(
            "/chat/image",
            files={"file": (filename, image_bytes, "image/jpeg")},
            data={"caption": caption},
        )
        r.raise_for_status()
        body = r.json()
        return body["reply"], body.get("proactive_question")

    async def send_audio(
        self, audio_bytes: bytes, filename: str
    ) -> Tuple[str, Optional[str]]:
        """POST /chat/audio → (reply, proactive_question | None)."""
        r = await self._http.post(
            "/chat/audio",
            files={"file": (filename, audio_bytes, "audio/ogg")},
        )
        r.raise_for_status()
        body = r.json()
        return body["reply"], body.get("proactive_question")

    # ── Teaching ──────────────────────────────────────────────────────────

    async def teach(self, topic: str, content: str) -> str:
        """POST /teach/ → acknowledgement reply."""
        r = await self._http.post(
            "/teach/", json={"topic": topic, "content": content}
        )
        r.raise_for_status()
        return r.json()["reply"]

    # ── Questions ─────────────────────────────────────────────────────────

    async def get_unanswered_questions(self) -> list:
        """GET /teach/questions → list of unanswered question dicts."""
        r = await self._http.get("/teach/questions")
        r.raise_for_status()
        return r.json()

    async def answer_question(self, question_id: int, answer: str) -> str:
        """POST /teach/questions/{id}/answer → acknowledgement reply."""
        r = await self._http.post(
            f"/teach/questions/{question_id}/answer",
            json={"answer": answer},
        )
        r.raise_for_status()
        return r.json()["reply"]

    async def get_knowledge(self) -> list:
        """GET /teach/knowledge → list of knowledge dicts."""
        r = await self._http.get("/teach/knowledge")
        r.raise_for_status()
        return r.json()

    async def get_tools(self) -> list:
        """GET /teach/tools → list of tool dicts."""
        r = await self._http.get("/teach/tools")
        r.raise_for_status()
        return r.json()
