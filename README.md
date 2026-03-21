# AI Child

> An autonomous learning AI that grows through conversation — just like a child.  
> **Note**: You will choose the AI's name when you first start using the system.

This AI starts with full language capability but zero personal knowledge.  
Through every conversation it accumulates memories, learns from what it is taught,  
and proactively asks questions when it wants to understand something better.

---

## 📚 文档导航

**新手必读**：👉 [📚_文档导航中心.md](📚_文档导航中心.md) - **所有文档已整理到 `docs/` 目录！**

### ⭐⭐⭐ 快速开始（5分钟）

| 我想... | 文档 | 时间 |
|--------|------|------|
| **30秒上手** | [docs/00_getting-started/⚡_30秒快速开始.md](docs/00_getting-started/⚡_30秒快速开始.md) | 2 分钟 |
| **完整启动** | [docs/00_getting-started/🚀_启动指南.md](docs/00_getting-started/🚀_启动指南.md) | 10 分钟 |

### ⭐⭐ 日常使用（常用参考）

| 我想... | 文档 | 时间 |
|--------|------|------|
| **人格配置** | [docs/01_usage/⚡_人格本地化快速参考.md](docs/01_usage/⚡_人格本地化快速参考.md) | 5 分钟 |
| **防幻觉工具** | [docs/01_usage/防幻觉工具速查表.md](docs/01_usage/防幻觉工具速查表.md) | 5 分钟 |
| **Token 成本** | [docs/💰_Token消耗分析与成本控制.md](docs/💰_Token消耗分析与成本控制.md) | 15 分钟 |

### ⭐ 深度理解（深入学习）

| 我想... | 文档 | 时间 |
|--------|------|------|
| **学习机制** | [docs/02_reference/AI_CHILD_学习机制深度研究.md](docs/02_reference/AI_CHILD_学习机制深度研究.md) | 45 分钟 |
| **防污染机制** | [docs/02_reference/🛡️_立场防污染守护机制.md](docs/02_reference/🛡️_立场防污染守护机制.md) | 30 分钟 |
| **人格隔离** | [docs/02_reference/📘_人格隔离本地化指南.md](docs/02_reference/📘_人格隔离本地化指南.md) | 40 分钟 |

**📂 浏览所有文档**: [`docs/` 目录结构](docs/)

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

The **server** is the brain.  your AI
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
| *(any text)* | Chat with your AI |
| *(photo)* | Send an image; it will describe and respond |
| *(voice message)* | Speak; it will transcribe and reply |
| `/teach <topic> \| <content>` | Teach the AI a new fact |
| `/questions` | List unanswered questions the AI has asked you |
| `/answer <id> <text>` | Answer one of its questions |
| `/knowledge` | Show everything the AI has been taught |

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

This AI is designed around a simple idea: **language is pre-installed, knowledge is not**.

- It never needs to be taught how to speak — GPT-4o provides that foundation.
- Everything else — who you are, what the world looks like, your favourite colour — it learns through conversation and explicit teaching.
- Like a child, it asks questions when it is curious, and remembers the answers.
- Memory is persistent: every conversation and every lesson survives a restart.

