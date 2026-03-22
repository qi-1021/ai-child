"""
AI Child Bot Bridge – entry point.

Run with:
    # Telegram bot only
    python main.py telegram

    # QQ bot only
    python main.py qq

    # Generic webhook server only
    python main.py webhook

    # All (default)
    python main.py
"""
import asyncio
import logging
import sys

import uvicorn

from adapters.telegram_bot import TelegramAdapter
from adapters.qq_bot import QQAdapter
from adapters.webhook import webhook_app
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_telegram():
    bot = TelegramAdapter()
    await bot.start()
    logger.info("Telegram bot running – press Ctrl-C to stop.")
    # Run until interrupted
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await bot.stop()


async def run_qq():
    bot = QQAdapter()
    await bot.start()
    logger.info("QQ bot running – press Ctrl-C to stop.")
    # Run until interrupted
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await bot.stop()


async def run_webhook():
    config = uvicorn.Config(
        webhook_app,
        host="0.0.0.0",
        port=settings.webhook_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_all():
    await asyncio.gather(
        run_telegram(),
        run_qq(),
        run_webhook(),
        return_exceptions=True,
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "telegram":
        asyncio.run(run_telegram())
    elif mode == "qq":
        asyncio.run(run_qq())
    elif mode == "webhook":
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_all())
