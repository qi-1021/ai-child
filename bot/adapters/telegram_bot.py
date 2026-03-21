"""
Telegram bot adapter for the AI Child.

This adapter lets users talk to the AI Child through Telegram – a free,
cross-platform messenger available on every smartphone.  No custom app
needs to be installed; the user just opens Telegram and chats with the bot.

Supported interactions
─────────────────────
Text        │ Send any text message → AI Child replies.
Photo       │ Send a photo (optional caption) → AI Child describes and replies.
Voice / Audio│ Record or send a voice message → transcribed then replied to.
/teach      │ /teach <topic> | <knowledge> – explicitly teach the AI Child.
/questions  │ List all unanswered proactive questions.
/answer     │ /answer <id> <text> – answer one of the AI Child's questions.
/knowledge  │ Show all knowledge the AI Child has accumulated.
/start      │ Greeting and help text.
/help       │ Same as /start.

Proactive questions
───────────────────
A background job polls the server every `question_poll_interval` seconds and
pushes any new unanswered questions to every known chat.
"""
import asyncio
import logging
from typing import Dict, Optional, Set

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from adapters.base import BaseAdapter
from adapters.server_client import ServerClient
from config import settings

logger = logging.getLogger(__name__)

# Track which question IDs have already been pushed so we don't repeat them.
_pushed_question_ids: Set[int] = set()


class TelegramAdapter(BaseAdapter):
    """Bridges Telegram ↔ AI Child server."""

    def __init__(self, token: str = ""):
        self._token = token or settings.telegram_token
        self._app: Application = (
            Application.builder().token(self._token).build()
        )
        # Map chat_id → last seen, used for broadcasting proactive questions.
        self._known_chats: Dict[int, bool] = {}
        self._poll_task: Optional[asyncio.Task] = None
        self._register_handlers()

    # ── BaseAdapter interface ──────────────────────────────────────────────

    async def send_message(self, chat_id: str, text: str) -> None:
        await self._app.bot.send_message(chat_id=int(chat_id), text=text)

    async def send_question(self, chat_id: str, question: str) -> None:
        await self._app.bot.send_message(
            chat_id=int(chat_id),
            text=f"🤔 小智想问你：\n{question}",
        )

    async def start(self) -> None:
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        self._poll_task = asyncio.create_task(self._question_poller())
        logger.info("Telegram bot started.")

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        logger.info("Telegram bot stopped.")

    # ── Handler registration ───────────────────────────────────────────────

    def _register_handlers(self) -> None:
        add = self._app.add_handler
        add(CommandHandler("start", self._cmd_start))
        add(CommandHandler("help", self._cmd_start))
        add(CommandHandler("teach", self._cmd_teach))
        add(CommandHandler("questions", self._cmd_questions))
        add(CommandHandler("answer", self._cmd_answer))
        add(CommandHandler("knowledge", self._cmd_knowledge))
        add(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))
        add(MessageHandler(filters.PHOTO, self._on_photo))
        add(MessageHandler(filters.VOICE | filters.AUDIO, self._on_audio))

    # ── Commands ───────────────────────────────────────────────────────────

    async def _cmd_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self._register_chat(update)
        await update.message.reply_text(
            "你好！我是小智 👋\n\n"
            "我是一个会持续学习的 AI，你可以：\n"
            "• 直接发消息和我聊天（支持文字、图片、语音）\n"
            "• /teach <主题> | <内容> — 教我新知识\n"
            "• /questions — 查看我想问你的问题\n"
            "• /answer <编号> <回答> — 回答我的问题\n"
            "• /knowledge — 查看我已学到的所有知识\n\n"
            "我会主动提问，帮助自己更好地认识世界！😊"
        )

    async def _cmd_teach(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self._register_chat(update)
        raw = " ".join(context.args or []).strip()
        if "|" not in raw:
            await update.message.reply_text(
                "格式：/teach <主题> | <内容>\n"
                "例：/teach 万有引力 | 牛顿发现物体之间存在相互吸引的力"
            )
            return

        topic, _, content = raw.partition("|")
        topic = topic.strip()
        content = content.strip()
        if not topic or not content:
            await update.message.reply_text("主题和内容都不能为空哦～")
            return

        await update.message.chat.send_action(ChatAction.TYPING)
        async with ServerClient() as srv:
            reply = await srv.teach(topic, content)
        await update.message.reply_text(reply)

    async def _cmd_questions(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self._register_chat(update)
        async with ServerClient() as srv:
            questions = await srv.get_unanswered_questions()
        if not questions:
            await update.message.reply_text("我现在没有想问你的问题～😊")
            return
        lines = [f"{q['id']}. {q['question']}" for q in questions]
        await update.message.reply_text(
            "🤔 我想问你这些问题：\n\n" + "\n".join(lines)
            + "\n\n用 /answer <编号> <回答> 来回答我哦"
        )

    async def _cmd_answer(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self._register_chat(update)
        args = context.args or []
        if len(args) < 2:
            await update.message.reply_text("格式：/answer <编号> <回答>")
            return
        try:
            question_id = int(args[0])
        except ValueError:
            await update.message.reply_text("编号必须是数字")
            return
        answer = " ".join(args[1:]).strip()
        await update.message.chat.send_action(ChatAction.TYPING)
        async with ServerClient() as srv:
            reply = await srv.answer_question(question_id, answer)
        await update.message.reply_text(reply)

    async def _cmd_knowledge(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self._register_chat(update)
        async with ServerClient() as srv:
            items = await srv.get_knowledge()
        if not items:
            await update.message.reply_text("我还没有学到任何知识～快来教我吧！")
            return
        lines = [f"• [{i['topic']}] {i['content'][:80]}" for i in items[:20]]
        suffix = f"\n…共 {len(items)} 条" if len(items) > 20 else ""
        await update.message.reply_text("📚 我已学到的知识：\n\n" + "\n".join(lines) + suffix)

    # ── Message handlers ───────────────────────────────────────────────────

    async def _on_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self._register_chat(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        async with ServerClient() as srv:
            reply, question = await srv.send_text(update.message.text or "")
        await update.message.reply_text(reply)
        if question:
            await update.message.reply_text(f"🤔 小智想问你：\n{question}")

    async def _on_photo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self._register_chat(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        # Choose the highest-resolution version of the photo
        photo = update.message.photo[-1]
        tg_file = await photo.get_file()
        image_bytes = await tg_file.download_as_bytearray()
        caption = update.message.caption or ""
        async with ServerClient() as srv:
            reply, question = await srv.send_image(
                bytes(image_bytes), filename="photo.jpg", caption=caption
            )
        await update.message.reply_text(reply)
        if question:
            await update.message.reply_text(f"🤔 小智想问你：\n{question}")

    async def _on_audio(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        self._register_chat(update)
        await update.message.chat.send_action(ChatAction.TYPING)
        voice = update.message.voice or update.message.audio
        tg_file = await voice.get_file()
        audio_bytes = await tg_file.download_as_bytearray()
        filename = getattr(voice, "file_name", None) or "voice.ogg"
        async with ServerClient() as srv:
            reply, question = await srv.send_audio(bytes(audio_bytes), filename=filename)
        await update.message.reply_text(reply)
        if question:
            await update.message.reply_text(f"🤔 小智想问你：\n{question}")

    # ── Proactive question poller ──────────────────────────────────────────

    async def _question_poller(self) -> None:
        """
        Periodically poll the server for new unanswered questions and push
        them to all known chats.
        """
        while True:
            await asyncio.sleep(settings.question_poll_interval)
            try:
                async with ServerClient() as srv:
                    questions = await srv.get_unanswered_questions()
                new = [
                    q for q in questions if q["id"] not in _pushed_question_ids
                ]
                for q in new:
                    _pushed_question_ids.add(q["id"])
                    for chat_id in list(self._known_chats):
                        await self.send_question(str(chat_id), q["question"])
            except Exception as exc:
                logger.warning("Question poll failed: %s", exc)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _register_chat(self, update: Update) -> None:
        """Remember this chat so proactive questions can be pushed."""
        if update.effective_chat:
            self._known_chats[update.effective_chat.id] = True
