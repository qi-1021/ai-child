"""
QQ bot adapter for the AI Child.

This adapter lets users talk to the AI Child through QQ messaging.
Supports text messaging through go-cqhttp or official QQ OpenAPI.

Setup:
------
1. Install go-cqhttp: https://github.com/Mrs4s/go-cqhttp
2. Configure go-cqhttp to enable HTTP API (usually on http://localhost:5700)
3. Set QQ_API_URL environment variable
4. Run this adapter: python main.py qq
"""
import asyncio
import logging
from typing import Dict, Optional, Set

import httpx

from adapters.base import BaseAdapter
from adapters.server_client import ServerClient
from config import settings

logger = logging.getLogger(__name__)

# Track which question IDs have already been pushed to avoid duplicates
_pushed_question_ids: Set[int] = set()


class QQAdapter(BaseAdapter):
    """Bridges QQ ↔ AI Child server via go-cqhttp HTTP API."""

    def __init__(self, api_url: str = ""):
        self._api_url = (api_url or settings.qq_api_url).rstrip("/")
        if not self._api_url:
            raise ValueError(
                "qq_api_url not configured. Set QQ_API_URL environment variable "
                "or provide api_url parameter."
            )
        self._client = httpx.AsyncClient(timeout=30.0)
        self._known_users: Dict[str, bool] = {}  # Track known QQ users
        self._known_groups: Dict[str, bool] = {}  # Track known QQ groups
        self._poll_task: Optional[asyncio.Task] = None
        logger.info(f"🤖 QQ 适配器初始化，API 地址: {self._api_url}")

    # ── BaseAdapter interface ──────────────────────────────────────────────

    async def send_message(self, chat_id: str, text: str) -> None:
        """Send a message to a QQ user or group. chat_id format: user_<qq> or group_<gid>"""
        try:
            if chat_id.startswith("user_"):
                qq_id = chat_id.replace("user_", "")
                await self._send_private_message(int(qq_id), text)
            elif chat_id.startswith("group_"):
                group_id = chat_id.replace("group_", "")
                await self._send_group_message(int(group_id), text)
            else:
                logger.warning(f"Unknown chat_id format: {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")

    async def send_question(self, chat_id: str, question: str) -> None:
        """Send a proactive question to a QQ user or group."""
        message = f"🤔 我想问你：\n{question}"
        await self.send_message(chat_id, message)

    async def start(self) -> None:
        """Start listening for QQ messages (polling)."""
        logger.info("🚀 QQ 适配器启动，开始监听消息...")
        self._poll_task = asyncio.create_task(self._message_loop())
        logger.info("✅ QQ 适配器已启动")

    async def stop(self) -> None:
        """Stop the adapter gracefully."""
        logger.info("停止 QQ 适配器...")
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()
        logger.info("QQ 适配器已停止")

    # ── Message sending ────────────────────────────────────────────────────

    async def _send_private_message(self, user_qq: int, text: str) -> None:
        """Send private message to a user."""
        try:
            resp = await self._client.post(
                f"{self._api_url}/send_private_msg",
                json={"user_id": user_qq, "message": text},
            )
            resp.raise_for_status()
            logger.debug(f"✓ 私聊消息已发送给 {user_qq}")
        except Exception as e:
            logger.error(f"Failed to send private message to {user_qq}: {e}")

    async def _send_group_message(self, group_id: int, text: str) -> None:
        """Send message to a group."""
        try:
            resp = await self._client.post(
                f"{self._api_url}/send_group_msg",
                json={"group_id": group_id, "message": text},
            )
            resp.raise_for_status()
            logger.debug(f"✓ 群消息已发送给 {group_id}")
        except Exception as e:
            logger.error(f"Failed to send group message to {group_id}: {e}")

    # ── Message processing ─────────────────────────────────────────────────

    async def _message_loop(self) -> None:
        """Main loop: poll for messages continuously."""
        message_id = 0
        while True:
            try:
                await asyncio.sleep(0.5)  # Poll every 500ms
                resp = await self._client.get(
                    f"{self._api_url}/get_msg",
                    params={"message_id": message_id},
                )
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") == "ok" and data.get("data"):
                    msg_data = data["data"]
                    await self._handle_message(msg_data)
                    message_id = msg_data.get("message_id", message_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message loop: {e}")
                await asyncio.sleep(2)

    async def _handle_message(self, msg_data: dict) -> None:
        """Process a single message from QQ."""
        try:
            msg_type = msg_data.get("message_type")  # "private" or "group"
            sender_id = msg_data.get("sender", {}).get("user_id")
            group_id = msg_data.get("group_id") if msg_type == "group" else None
            content = msg_data.get("message", "")

            if not sender_id or not content:
                return

            # Track known users/groups
            if msg_type == "private":
                self._known_users[f"user_{sender_id}"] = True
                chat_id = f"user_{sender_id}"
            elif msg_type == "group":
                self._known_groups[f"group_{group_id}"] = True
                chat_id = f"group_{group_id}"
            else:
                return

            logger.info(f"📨 来自 {chat_id}: {content[:50]}")

            # Send to AI Child server
            async with ServerClient() as srv:
                reply, question = await srv.send_text(content)

            # Send reply back
            reply_msg = f"🤖 {reply}"
            if question:
                reply_msg += f"\n\n🤔 我想问你：{question}"

            await self.send_message(chat_id, reply_msg)

        except Exception as e:
            logger.error(f"Failed to handle message: {e}")

    async def _question_poller(self) -> None:
        """Periodically poll for new proactive questions and push them."""
        while True:
            try:
                await asyncio.sleep(settings.question_poll_interval)
                async with ServerClient() as srv:
                    questions = await srv.get_unanswered_questions()

                # Find new, unpushed questions
                new_questions = [
                    q for q in questions if q["id"] not in _pushed_question_ids
                ]

                # Push to all known users and groups
                for q in new_questions:
                    _pushed_question_ids.add(q["id"])
                    question_text = q["question"]
                    logger.info(f"📢 推送主动问题：{question_text[:50]}")

                    # Notify all known users
                    for user_chat_id in list(self._known_users):
                        await self.send_question(user_chat_id, question_text)

                    # Notify all known groups
                    for group_chat_id in list(self._known_groups):
                        await self.send_question(group_chat_id, question_text)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in question poller: {e}")
