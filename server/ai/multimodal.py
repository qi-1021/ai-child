"""
Multi-modal processing utilities:
  - Transcribe audio to text using Whisper
  - Describe / analyse images using GPT-4o Vision
  - Convert text to speech using TTS-1
"""
import base64
import io
import logging
import os
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)


def save_media(data: bytes, filename: str) -> str:
    """Save raw media bytes and return the relative path."""
    path = MEDIA_DIR / filename
    path.write_bytes(data)
    return str(path)


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Transcribe raw audio bytes to text using OpenAI Whisper."""
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename
    transcript = await client.audio.transcriptions.create(
        model=settings.openai_whisper_model,
        file=audio_file,
    )
    return transcript.text


async def describe_image(image_bytes: bytes) -> str:
    """Return a textual description of an image using GPT-4o vision."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    response = await client.chat.completions.create(
        model=settings.openai_vision_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "auto",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Please describe this image in detail. "
                            "What do you see? What is happening?"
                        ),
                    },
                ],
            }
        ],
        max_tokens=512,
    )
    return response.choices[0].message.content or ""


async def text_to_speech(text: str) -> bytes:
    """Convert text to audio bytes using OpenAI TTS."""
    response = await client.audio.speech.create(
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        input=text,
    )
    return response.content
