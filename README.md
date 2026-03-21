# AI Child (小智)

> An autonomous learning AI that grows through conversation — just like a child.

小智 starts with full language capability but zero personal knowledge.  
Through every conversation it accumulates memories, learns from what it is taught,  
and proactively asks questions when it wants to understand something better.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        AI Child Server                        │
│  (Windows / macOS, Python + FastAPI, runs on your computer)  │
│                                                              │
│  ┌─────────────────┐   ┌─────────────────┐                  │
│  │  AI Child Core  │   │  SQLite Memory  │                  │
│  │  (GPT-4o base)  │◄──│  conversations  │                  │
│  │  + proactive    │   │  knowledge base │                  │
│  │    questions    │   │  pending Qs     │                  │
│  └────────┬────────┘   └─────────────────┘                  │
│           │ REST API + WebSocket                              │
└───────────┼──────────────────────────────────────────────────┘
            │
     ┌──────┴──────────────────────────────┐
     │         Bot Bridge Layer             │
     │  (bot/ — runs alongside the server)  │
     │                                      │
     │  ┌──────────────┐  ┌─────────────┐  │
     │  │ Telegram Bot │  │  Generic    │  │
     │  │  (text /     │  │  Webhook    │  │
     │  │   photo /    │  │  Receiver   │  │
     │  │   voice)     │  │  (HTTP API) │  │
     │  └──────┬───────┘  └──────┬──────┘  │
     └─────────┼─────────────────┼──────────┘
               │                 │
         Telegram app      Any chat platform
         (iOS / Android)   (WeChat, Discord, …)
```

The **server** is the brain.  
The **bot bridge** is what lets you talk to 小智 from your phone — no custom app needed.  
Just open Telegram (or your platform of choice) and start chatting.

---

## Features

| Capability | Details |
|---|---|
| 🗣️ Text | Full natural language conversation |
| 🖼️ Image | Send a photo; 小智 describes it and responds |
| 🎙️ Voice | Record a voice message; automatically transcribed then replied to |
| 📚 Teaching | Explicitly teach facts; 小智 remembers them forever |
| 🤔 Proactive questions | 小智 asks when it is curious — you can answer via chat |
| 💾 Persistent memory | All conversations and knowledge survive restarts |
| 🔌 Extensible | Webhook bridge lets any platform integrate in minutes |

---

## Quick Start

### 1 — Prerequisites

- Python 3.11+
- An [OpenAI API key](https://platform.openai.com/api-keys)
- A Telegram bot token from [@BotFather](https://t.me/botfather) *(optional — only needed for Telegram)*

---

### 2 — Run the server

```bash
cd server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Create a .env file (copy and edit)
cat > .env <<'EOF'
OPENAI_API_KEY=sk-...
EOF

python main.py
# → http://localhost:8000  (interactive docs at /docs)
```

---

### 3 — Run the bot bridge

```bash
cd bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cat > .env <<'EOF'
SERVER_URL=http://localhost:8000
TELEGRAM_TOKEN=<your-bot-token>
WEBHOOK_SECRET=<choose-a-secret>   # optional
EOF

# Start Telegram bot + generic webhook server
python main.py

# Or start only one adapter:
python main.py telegram
python main.py webhook
```

---

## Telegram Commands

| Command | Description |
|---|---|
| *(any text)* | Chat with 小智 |
| *(photo)* | Send an image; 小智 will describe and respond |
| *(voice message)* | Speak; 小智 will transcribe and reply |
| `/teach <topic> \| <content>` | Teach 小智 a new fact |
| `/questions` | List unanswered questions 小智 has asked you |
| `/answer <id> <text>` | Answer one of 小智's questions |
| `/knowledge` | Show everything 小智 has been taught |

---

## Generic Webhook API

The webhook bridge (`bot/adapters/webhook.py`) runs on port **8001** and accepts requests from any platform.

### Send a message

```http
POST /webhook/message
Content-Type: application/json

{
  "chat_id":  "user-123",
  "type":     "text",          // "text" | "image_url" | "audio_url"
  "content":  "Hello!",
  "secret":   "your-secret"   // optional
}
```

Response:

```json
{
  "reply": "Hi! I'm 小智 ...",
  "proactive_question": "What do you like to do for fun?"
}
```

### Other endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/webhook/questions` | List unanswered proactive questions |
| `POST` | `/webhook/teach` | Teach a new knowledge item |
| `GET` | `/health` | Health check |

---

## Server REST API

Full interactive docs available at **http://localhost:8000/docs** when the server is running.

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat/text` | Send a text message |
| `POST` | `/chat/image` | Send an image (multipart) |
| `POST` | `/chat/audio` | Send audio (multipart) |
| `GET` | `/chat/history` | Retrieve conversation history |
| `GET` | `/chat/audio/{id}` | TTS: get an assistant reply as audio |
| `POST` | `/teach/` | Teach a knowledge item |
| `GET` | `/teach/knowledge` | List all knowledge items |
| `GET` | `/teach/questions` | List unanswered proactive questions |
| `POST` | `/teach/questions/{id}/answer` | Answer a proactive question |

---

## Running Tests

```bash
# Server tests
cd server
python -m pytest tests/ -v --asyncio-mode=auto

# Bot bridge tests
cd bot
python -m pytest tests/ -v --asyncio-mode=auto
```

---

## Project Layout

```
ai-child/
├── server/                  # AI Child core server
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings (env-based)
│   ├── ai/
│   │   ├── child.py         # Core chat + proactive question logic
│   │   ├── memory.py        # DB helpers (conversations, knowledge, questions)
│   │   └── multimodal.py    # Image description, audio transcription, TTS
│   ├── api/
│   │   ├── chat.py          # Chat endpoints + WebSocket
│   │   └── teach.py         # Teaching + knowledge endpoints
│   ├── models/
│   │   ├── __init__.py      # SQLAlchemy models + DB init
│   │   └── schemas.py       # Pydantic request/response schemas
│   └── tests/
│       └── test_server.py
│
└── bot/                     # Chat platform bridge
    ├── main.py              # Entry point (telegram / webhook / all)
    ├── config.py            # Bot settings
    ├── adapters/
    │   ├── base.py          # Abstract adapter interface
    │   ├── server_client.py # HTTP client for the server API
    │   ├── telegram_bot.py  # Telegram adapter
    │   └── webhook.py       # Generic webhook receiver
    └── tests/
        └── test_bot.py
```

---

## Design Philosophy

小智 is designed around a simple idea: **language is pre-installed, knowledge is not**.

- 小智 never needs to be taught how to speak — GPT-4o provides that foundation.
- Everything else — who you are, what the world looks like, your favourite colour — 小智 learns through conversation and explicit teaching.
- Like a child, 小智 asks questions when it is curious, and remembers the answers.
- Memory is persistent: every conversation and every lesson survives a restart.

