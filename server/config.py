"""
Configuration settings for AI Child server.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI API key – set via environment variable OPENAI_API_KEY
    openai_api_key: str = ""

    # Model to use as the base intelligence
    openai_model: str = "gpt-4o"

    # Vision model (supports images)
    openai_vision_model: str = "gpt-4o"

    # Audio transcription model
    openai_whisper_model: str = "whisper-1"

    # Text-to-speech model
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"

    # SQLite database file for persistent memory
    database_url: str = "sqlite+aiosqlite:///./ai_child.db"

    # How many past conversation turns to include as context
    memory_context_turns: int = 20

    # How often (in conversation turns) the AI child proactively asks a question
    proactive_question_interval: int = 5

    # JWT settings for client authentication
    secret_key: str = "CHANGE_THIS_SECRET_IN_PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 1 week

    # Server host and port
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Autonomous research ────────────────────────────────────────────────
    # Enable web search after answering a proactive question
    research_enabled: bool = True

    # Number of search queries generated per research session
    research_query_count: int = 2

    # DuckDuckGo results fetched per query
    research_max_results: int = 3

    # ── Code sandbox ───────────────────────────────────────────────────────
    # Seconds before a sandboxed subprocess is killed
    code_exec_timeout: int = 10

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
