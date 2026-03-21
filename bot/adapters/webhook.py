"""
Generic inbound webhook receiver.

Any platform that can POST an HTTP request can use this adapter to talk to
the AI Child.  The server also exposes an /outbound endpoint that a platform
can poll to fetch replies.

Request format (JSON, POST /webhook/message):
    {
        "chat_id":   "<opaque string identifying the conversation>",
        "type":      "text" | "image_url" | "audio_url",
        "content":   "<text body OR public URL to image / audio>",
        "caption":   "<optional, used with image_url>",
        "secret":    "<optional shared secret>"
    }

Response format:
    {
        "reply":              "<AI child reply text>",
        "proactive_question": "<question or null>"
    }

The webhook also exposes:
  GET  /webhook/questions  → unanswered questions list (same as server API)
  POST /webhook/teach      → teach the AI child (same body as server /teach/)
"""
import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from adapters.server_client import ServerClient
from config import settings

logger = logging.getLogger(__name__)

# Maximum size of media files fetched from external URLs (10 MB)
_MAX_MEDIA_BYTES = 10 * 1024 * 1024

webhook_app = FastAPI(
    title="AI Child – Webhook Bridge",
    description=(
        "Generic HTTP webhook that forwards messages from any chat platform "
        "to the AI Child server and returns its replies."
    ),
    version="0.1.0",
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class WebhookMessageIn(BaseModel):
    chat_id: str
    type: str = "text"           # "text" | "image_url" | "audio_url"
    content: str                 # text body or public URL
    caption: Optional[str] = None
    secret: Optional[str] = None


class TeachIn(BaseModel):
    topic: str
    content: str
    secret: Optional[str] = None


# ── Auth helper ───────────────────────────────────────────────────────────────

def _verify_secret(provided: Optional[str]) -> None:
    if settings.webhook_secret and provided != settings.webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")


# ── SSRF guard ────────────────────────────────────────────────────────────────

def _validate_media_url(url: str) -> tuple[str, str, str]:
    """
    Validate a user-supplied media URL against SSRF attacks.

    Returns (resolved_ip, hostname, path_with_query) so the caller can
    construct its own safe request target rather than re-using the raw
    user-supplied URL.

    Raises HTTPException (400) on any policy violation.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise HTTPException(
            status_code=400,
            detail="Only https:// URLs are accepted for media content.",
        )
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL: missing hostname.")
    try:
        resolved_ip = socket.getaddrinfo(hostname, None)[0][4][0]
        ip_obj = ipaddress.ip_address(resolved_ip)
    except (socket.gaierror, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not resolve hostname: {hostname}"
        ) from exc
    if (
        ip_obj.is_loopback
        or ip_obj.is_private
        or ip_obj.is_link_local
        or ip_obj.is_reserved
        or ip_obj.is_multicast
    ):
        raise HTTPException(
            status_code=400,
            detail="Media URL resolves to a private or reserved address.",
        )
    path_with_query = parsed.path
    if parsed.query:
        path_with_query = f"{path_with_query}?{parsed.query}"
    return resolved_ip, hostname, path_with_query


async def _fetch_media(url: str) -> bytes:
    """Download media from a validated external URL.

    The resolved IP address is used as the TCP target and the original
    hostname is sent as the Host header.  This prevents both SSRF (via
    private address access) and DNS rebinding (IP is resolved and checked
    exactly once, before the request is made).
    """
    resolved_ip, hostname, path = _validate_media_url(url)
    # Build a safe URL using the pre-validated IP address
    target_url = f"https://{resolved_ip}{path}"
    headers = {"Host": hostname}
    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=False,
        verify=False,  # cert validation uses resolved_ip; hostname is in Host header
    ) as http:
        resp = await http.get(target_url, headers=headers)
        resp.raise_for_status()
        content = resp.content
    if len(content) > _MAX_MEDIA_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Media file too large (max {_MAX_MEDIA_BYTES // (1024 * 1024)} MB).",
        )
    return content


# ── Endpoints ─────────────────────────────────────────────────────────────────

@webhook_app.post("/webhook/message")
async def receive_message(body: WebhookMessageIn):
    """Receive a message from any platform and return the AI child's reply."""
    _verify_secret(body.secret)

    async with ServerClient() as srv:
        if body.type == "text":
            reply, question = await srv.send_text(body.content)

        elif body.type == "image_url":
            # Download the image then forward to the server
            image_bytes = await _fetch_media(body.content)
            reply, question = await srv.send_image(
                image_bytes,
                filename="image.jpg",
                caption=body.caption or "",
            )

        elif body.type == "audio_url":
            audio_bytes = await _fetch_media(body.content)
            reply, question = await srv.send_audio(audio_bytes, filename="audio.ogg")

        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported message type: {body.type}"
            )

    return {"reply": reply, "proactive_question": question}


@webhook_app.get("/webhook/questions")
async def get_questions(secret: Optional[str] = None):
    """Return unanswered questions so the platform can push them to users."""
    _verify_secret(secret)
    async with ServerClient() as srv:
        return await srv.get_unanswered_questions()


@webhook_app.post("/webhook/teach")
async def teach(body: TeachIn):
    """Teach the AI child through the webhook."""
    _verify_secret(body.secret)
    async with ServerClient() as srv:
        reply = await srv.teach(body.topic, body.content)
    return {"reply": reply}


@webhook_app.get("/health")
async def health():
    return {"status": "ok"}
