"""
Configuration settings for AI Child server.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── LLM Provider Selection ──────────────────────────────────────────────
    # Choose between "openai", "dashscope" (阿里云百炼), or "ollama" (本地部署)
    llm_provider: str = "openai"

    # ── OpenAI Configuration ────────────────────────────────────────────────
    # OpenAI API key – set via environment variable OPENAI_API_KEY
    openai_api_key: str = ""

    # Custom OpenAI base URL (e.g., for using OpenAI-compatible APIs)
    openai_base_url: str = ""

    # Model to use as the base intelligence
    openai_model: str = "gpt-4o"

    # Vision model (supports images)
    openai_vision_model: str = "gpt-4o"

    # Audio transcription model
    openai_whisper_model: str = "whisper-1"

    # Text-to-speech model
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"

    # ── DashScope (阿里云百炼) Configuration ────────────────────────────────
    # DashScope API key – set via environment variable DASHSCOPE_API_KEY
    dashscope_api_key: str = ""

    # DashScope model name (e.g., "qwen3.5-35b-a3b")
    dashscope_model: str = "qwen3.5-35b-a3b"

    # ── Ollama (本地全量部署) Configuration ──────────────────────────────────
    # Ollama exposes an OpenAI-compatible REST API at localhost:11434.
    # Set LLM_PROVIDER=ollama to run the entire stack with no cloud dependency.
    #
    # Quick-start:
    #   1. Install Ollama  →  https://ollama.com
    #   2. ollama pull llama3.2        # main chat model
    #   3. ollama pull nomic-embed-text # embedding model
    #   4. Set env:  LLM_PROVIDER=ollama
    #   5. Start server normally — no API keys required.
    ollama_base_url: str = "http://localhost:11434/v1"

    # Main chat / instruction model served by Ollama
    ollama_model: str = "llama3.2"

    # Embedding model served by Ollama (supports /v1/embeddings since 0.1.26+)
    ollama_embedding_model: str = "nomic-embed-text"

    # SQLite database file for persistent memory
    database_url: str = "sqlite+aiosqlite:///./ai_child.db"

    # How many past conversation turns to include as context
    memory_context_turns: int = 20

    # How often (in conversation turns) the AI child proactively asks a question.
    # Set to 2 so the AI asks something almost every other turn — like a curious child.
    proactive_question_interval: int = 2

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
    research_query_count: int = 3

    # DuckDuckGo results fetched per query
    research_max_results: int = 4

    # ── Code sandbox ───────────────────────────────────────────────────────
    # Seconds before a sandboxed subprocess is killed
    code_exec_timeout: int = 10

    # ── Memory / Embedding ─────────────────────────────────────────────────────
    # OpenAI / DashScope embedding model for semantic (vector) memory search.
    # For DashScope set to "text-embedding-v3".
    # For Ollama this is overridden by ollama_embedding_model above.
    embedding_model: str = "text-embedding-3-small"

    # Minimum cosine similarity [0.0–1.0] for a knowledge item to be considered
    # relevant in semantic search. Lower = more permissive.
    embedding_min_similarity: float = 0.30

    # ── Few-shot self-teaching ─────────────────────────────────────────────────
    # Enable the child-like inference engine that generates hypotheses after
    # every user teaching event (like a child who generalises from a few examples).
    few_shot_enabled: bool = True

    # How many inferences to generate per teaching event (1–5 recommended).
    few_shot_inference_count: int = 2

    # Confidence assigned to self-generated inferences (0-100).
    # Lower than user-sourced facts (100) because they are hypotheses, not facts.
    few_shot_confidence: int = 50

    # ── Sleep cycle ───────────────────────────────────────────────────────────
    # Enable/disable the human-like sleep/wake cycle
    sleep_enabled: bool = True

    # Bedtime hour in 24-h format (local time per ai_timezone)
    sleep_hour: int = 22   # 10 PM

    # Wake-up hour in 24-h format
    wake_hour: int = 7     # 7 AM

    # IANA timezone for the sleep schedule
    ai_timezone: str = "Asia/Shanghai"

    # ── Dream phase (sleep-time model strengthening) ──────────────────────────
    # Export a JSONL fine-tuning dataset after each sleep consolidation.
    # The file can be fed into OpenAI fine-tuning, Axolotl, LLaMA-Factory, etc.
    sleep_export_training_data: bool = True

    # Directory where per-night training JSONL files are written.
    training_data_dir: str = "./training_data"

    # For Ollama only: after each sleep cycle, bake high-confidence knowledge
    # into a new Modelfile and create a strengthened model generation.
    # Requires llm_provider="ollama" and the Ollama daemon to be running.
    # The newly created model becomes the active model for the next session.
    sleep_create_ollama_generation: bool = False

    # Prefix used when naming Ollama model generations (e.g., "aichild" →
    # "aichild-gen1", "aichild-gen2", …).
    ollama_generation_prefix: str = "aichild"

    # ── Social media / RSS learning ───────────────────────────────────────────
    # Enable the RSS-based social media learning pipeline.
    # When enabled, the AI reads subscribed RSS/Atom feeds and learns from them
    # just like a child reading the news each morning.
    social_learning_enabled: bool = True

    # How often (in minutes) to poll subscribed RSS feeds for new content.
    rss_poll_interval_minutes: int = 60

    # Use the LLM to summarise each RSS item into concise knowledge (recommended).
    # If False, the raw item description is stored directly without summarisation.
    rss_summarise_enabled: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
