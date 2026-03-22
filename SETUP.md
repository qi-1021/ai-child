# 🚀 AI Child Setup Guide

Welcome to AI Child! This guide will help you set up the system either with the interactive wizard or manually.

## Quick Start (Recommended)

### Option 1: Automated Setup Wizard (Easiest)

```bash
# Make the setup script executable
chmod +x setup.sh

# Run the interactive setup wizard
./setup.sh
# or
python3 setup_wizard.py
```

The wizard will guide you through:
- ✅ Choosing an LLM provider (Local Ollama or Cloud)
- ✅ Installing/configuring Ollama (if choosing local)
- ✅ Setting up bot adapters (Telegram, QQ)
- ✅ Generating `.env` configuration files
- ✅ Validating your setup

### Option 2: Manual Setup

#### 1. Choose Your LLM Provider

**A. Local Deployment (Ollama) - Recommended**

```bash
# Install Ollama from https://ollama.com

# Start Ollama server
ollama serve

# In another terminal, pull a model
ollama pull qwen2  # or another model

# Copy server/.env.example to server/.env
cp server/.env.example server/.env

# Edit server/.env and set:
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2
```

**B. Cloud Deployment (OpenAI)**

```bash
# Copy server/.env.example to server/.env
cp server/.env.example server/.env

# Edit server/.env and set:
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4
```

**C. Cloud Deployment (DashScope/阿里云)**

```bash
# Copy server/.env.example to server/.env
cp server/.env.example server/.env

# Edit server/.env and set:
LLM_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-your-key-here
DASHSCOPE_MODEL=qwen3.5-35b-a3b
```

#### 2. Setup Bot Adapters

```bash
# Copy bot/.env.example to bot/.env
cp bot/.env.example bot/.env

# Edit bot/.env
```

**For QQ Bot:**
```bash
# Install go-cqhttp: https://github.com/Mrs4s/go-cqhttp
# Configure go-cqhttp with HTTP API on port 5700

# Edit bot/.env:
QQ_API_URL=http://localhost:5700
```

**For Telegram Bot:**
```bash
# Create bot with @BotFather on Telegram

# Edit bot/.env:
TELEGRAM_TOKEN=your-token-here
```

#### 3. Install Dependencies

```bash
# Server dependencies
cd server
pip install -r requirements.txt

# Bot dependencies
cd ../bot
pip install -r requirements.txt
```

---

## Running the System

### Terminal 1: Start Ollama (if using local Ollama)
```bash
ollama serve
```

### Terminal 2: Start AI Child Server
```bash
cd server
python3 main.py
```

Verify it's running:
```bash
curl http://localhost:8000/health
```

### Terminal 3: Start Bots

**Option A: Start all bots**
```bash
cd bot
python3 main.py
```

**Option B: Start only QQ bot**
```bash
cd bot
python3 main.py qq
```

**Option C: Start only Telegram bot**
```bash
cd bot
python3 main.py telegram
```

---

## Accessing the System

### Web UI (Chat Interface)
```
http://localhost:8000
```

### API Documentation
```
http://localhost:8000/docs
```

---

## Configuration Files

### Server Configuration: `server/.env`

| Setting | Options | Default |
|---------|---------|---------|
| `LLM_PROVIDER` | `ollama`, `openai`, `dashscope` | `ollama` |
| `OLLAMA_MODEL` | Any Ollama model | `qwen2` |
| `OLLAMA_BASE_URL` | Ollama API endpoint | `http://localhost:11434/v1` |
| `OPENAI_API_KEY` | Your OpenAI API key | - |
| `DASHSCOPE_API_KEY` | Your DashScope API key | - |
| `PORT` | Server port | `8000` |
| `SLEEP_ENABLED` | `true`/`false` | `true` |
| `SLEEP_HOUR` | Sleep time (0-23) | `22` |
| `WAKE_HOUR` | Wake time (0-23) | `7` |
| `AI_TIMEZONE` | IANA timezone | `Asia/Shanghai` |

### Bot Configuration: `bot/.env`

| Setting | Description |
|---------|-------------|
| `SERVER_URL` | AI Child server URL | `http://localhost:8000` |
| `TELEGRAM_TOKEN` | Telegram bot token | - |
| `QQ_API_URL` | go-cqhttp HTTP API URL | `http://localhost:5700` |
| `QQ_API_TOKEN` | Optional QQ API token | - |
| `QUESTION_POLL_INTERVAL` | Seconds between polls | `60` |
| `WEBHOOK_PORT` | Webhook server port | `8001` |

---

## Troubleshooting

### "Ollama is not running"
```bash
# In a new terminal:
ollama serve
```

### "Cannot connect to server"
```bash
# Check if server is running:
curl http://localhost:8000/health

# If not, start it:
cd server
python3 main.py
```

### "QQ_API_URL not configured"
```bash
# Make sure bot/.env exists and has:
QQ_API_URL=http://localhost:5700

# Make sure go-cqhttp is running:
# Check go-cqhttp configuration
```

### "No module named 'fastapi'"
```bash
# Install dependencies:
cd server
pip install -r requirements.txt

cd ../bot
pip install -r requirements.txt
```

### API keys in git history

⚠️ **IMPORTANT**: Never commit `.env` files containing API keys!

```bash
# These files are already excluded:
cat .gitignore | grep -A 5 "Environment"

# If you accidentally committed sensitive data:
# See: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
```

---

## Environment Variables

All configuration can also be set via environment variables:

```bash
# Server
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=qwen2
export PORT=8000

# Bot
export QQ_API_URL=http://localhost:5700
export TELEGRAM_TOKEN=your-token

# Then run:
cd server && python3 main.py &
cd bot && python3 main.py
```

---

## Next Steps

1. **Explore the Web UI**: Visit http://localhost:8000 to chat with AI
2. **View API Docs**: Check http://localhost:8000/docs for available endpoints
3. **Start QQ Bot**: Talk to the bot in QQ groups/private chats
4. **Review Code**: Check out `server/` and `bot/adapters/` to understand the architecture

---

## Support

- 📚 Documentation: See `README.md`
- 🐛 Issues: Report on GitHub
- 💬 Discussions: Open an issue for questions

Happy chatting! 🎉
