"""
Abstract base class for chat platform adapters.

Every adapter must be able to:
  - send_message(chat_id, text) → deliver a text reply to the user.
  - send_question(chat_id, question_text) → push a proactive question.

The adapter implementation decides which chat_id (user / group) to target.
"""
from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """Interface every platform adapter must implement."""

    @abstractmethod
    async def send_message(self, chat_id: str, text: str) -> None:
        """Send a plain-text message to a chat."""

    @abstractmethod
    async def send_question(self, chat_id: str, question: str) -> None:
        """Push a proactive question from the AI child to a chat."""

    @abstractmethod
    async def start(self) -> None:
        """Start listening for incoming messages (blocking or background)."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the adapter."""
