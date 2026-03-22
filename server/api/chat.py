"""
Chat REST endpoints and WebSocket handler.
"""
import logging
import uuid
from datetime import datetime
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ai.child import chat
from ai.memory import get_recent_messages
from ai.multimodal import describe_image, save_media, transcribe_audio, text_to_speech
from models import get_session
from models.schemas import ConversationHistory, MessageOut, WSEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/history", response_model=ConversationHistory)
async def get_history(
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """Return the most recent conversation turns."""
    msgs = await get_recent_messages(session, limit=limit)
    return ConversationHistory(
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                content_type=m.content_type,
                timestamp=m.timestamp,
                media_url=f"/media/{m.media_path}" if m.media_path else None,
            )
            for m in msgs
        ],
        total=len(msgs),
    )


@router.post("/text", response_model=dict)
async def send_text(
    text: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    """Send a plain-text message and get a reply."""
    reply, question = await chat(session, text, content_type="text")
    return {"reply": reply, "proactive_question": question}


@router.post("/image", response_model=dict)
async def send_image(
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    session: AsyncSession = Depends(get_session),
):
    """Send an image (with optional caption) and get a reply."""
    image_bytes = await file.read()
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    media_path = save_media(image_bytes, filename)

    # Describe the image and combine with caption
    description = await describe_image(image_bytes)
    user_text = description
    if caption:
        user_text = f"{caption}\n\n[Image content: {description}]"

    reply, question = await chat(
        session, user_text, content_type="image", media_path=media_path
    )
    return {"reply": reply, "proactive_question": question, "image_description": description}


@router.post("/audio", response_model=dict)
async def send_audio(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Send audio, transcribe it, and get a reply."""
    audio_bytes = await file.read()
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    media_path = save_media(audio_bytes, filename)

    transcription = await transcribe_audio(audio_bytes, filename=file.filename or "audio.wav")

    reply, question = await chat(
        session, transcription, content_type="audio", media_path=media_path
    )
    return {
        "reply": reply,
        "proactive_question": question,
        "transcription": transcription,
    }


@router.get("/audio/{message_id}")
async def get_audio_reply(
    message_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Convert the AI reply for a given message ID to audio and return it."""
    from fastapi.responses import Response
    from ai.memory import get_recent_messages
    msgs = await get_recent_messages(session, limit=200)
    msg = next((m for m in msgs if m.id == message_id and m.role == "assistant"), None)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    audio_bytes = await text_to_speech(msg.content)
    return Response(content=audio_bytes, media_type="audio/mpeg")


# ── WebSocket ─────────────────────────────────────────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, event: dict):
        for ws in list(self.active):
            try:
                await ws.send_json(event)
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket endpoint for real-time bidirectional communication.

    Client sends:
      {"type": "text", "payload": {"text": "..."}}
      {"type": "ping"}

    Server sends:
      {"type": "message",  "payload": {"id": .., "role": "assistant", "content": "...", ...}}
      {"type": "question", "payload": {"id": .., "question": "..."}}
      {"type": "ack",      "payload": {}}
      {"type": "error",    "payload": {"detail": "..."}}
    """
    await manager.connect(ws)
    logger.info("WebSocket client connected. Total: %d", len(manager.active))
    async with _ws_session(ws):
        pass


async def _ws_session(ws: WebSocket):
    """Inner coroutine handling WebSocket lifecycle with its own DB session."""
    from models import async_session

    try:
        async with async_session() as session:
            while True:
                data = await ws.receive_json()
                event_type = data.get("type")

                if event_type == "ping":
                    await ws.send_json({"type": "ack", "payload": {}})
                    continue

                if event_type == "text":
                    text = (data.get("payload") or {}).get("text", "").strip()
                    if not text:
                        await ws.send_json(
                            {"type": "error", "payload": {"detail": "Empty message"}}
                        )
                        continue

                    reply, question = await chat(session, text)

                    await ws.send_json(
                        {
                            "type": "message",
                            "payload": {
                                "role": "assistant",
                                "content": reply,
                                "timestamp": datetime.utcnow().isoformat(),
                            },
                        }
                    )
                    if question:
                        await ws.send_json(
                            {
                                "type": "question",
                                "payload": {"question": question},
                            }
                        )
                else:
                    await ws.send_json(
                        {
                            "type": "error",
                            "payload": {"detail": f"Unknown event type: {event_type}"},
                        }
                    )
    except WebSocketDisconnect:
        manager.disconnect(ws)
        logger.info("WebSocket client disconnected.")
    except Exception as exc:
        logger.exception("WebSocket error: %s", exc)
        manager.disconnect(ws)
