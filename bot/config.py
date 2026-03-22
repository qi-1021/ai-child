"""
Configuration for the AI Child bot bridge.
"""
from pydantic_settings import BaseSettings


class BotSettings(BaseSettings):
    # ── AI Child server ────────────────────────────────────────────────────
    # Base URL of the running AI Child server (server/main.py)
    server_url: str = "http://localhost:8000"

    # ── Telegram ───────────────────────────────────────────────────────────
    # Obtain from @BotFather on Telegram
    telegram_token: str = ""

    # ── QQ (go-cqhttp) ────────────────────────────────────────────────────
    # HTTP API URL of go-cqhttp (usually http://localhost:5700)
    qq_api_url: str = ""

    # Optional token for QQ API authentication
    qq_api_token: str = ""

    # How often (seconds) to poll the server for new proactive questions
    # and push them to connected users.
    question_poll_interval: int = 60

    # ── Webhook receiver (generic inbound) ────────────────────────────────
    # Port for the lightweight webhook HTTP server
    webhook_port: int = 8001

    # Optional secret token required in incoming webhook requests
    webhook_secret: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = BotSettings()
