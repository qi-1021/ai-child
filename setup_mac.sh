#!/usr/bin/env bash
# setup_mac.sh — One-shot setup for AI Child on M4 MacBook Air (macOS / Apple Silicon)
# Usage: bash setup_mac.sh
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RESET="\033[0m"

info()    { echo -e "${CYAN}ℹ ${RESET}$*"; }
success() { echo -e "${GREEN}✔ ${RESET}$*"; }
warn()    { echo -e "${YELLOW}⚠ ${RESET}$*"; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

header "🤖  AI Child — macOS / Apple Silicon Setup"

# ── 1. Homebrew ────────────────────────────────────────────────────────────────
header "1/6  Homebrew"
if command -v brew &>/dev/null; then
    success "Homebrew already installed."
else
    info "Installing Homebrew …"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add Homebrew to PATH for Apple Silicon
    eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
fi

# ── 2. System dependencies ─────────────────────────────────────────────────────
header "2/6  System dependencies (ffmpeg)"
# ffmpeg: converts audio formats (Telegram sends OGG; OpenAI Whisper accepts it,
#         but ffmpeg is handy for debugging and other audio work)
brew install ffmpeg 2>/dev/null || warn "ffmpeg already installed or skipped."
success "System dependencies ready."

# ── 3. Python ──────────────────────────────────────────────────────────────────
header "3/6  Python"
PYTHON=""
for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done
if [[ -z "$PYTHON" ]]; then
    info "Python 3.12 not found — installing via Homebrew …"
    brew install python@3.12
    PYTHON="python3.12"
fi
PY_VERSION=$("$PYTHON" --version)
success "Using $PY_VERSION at $(command -v "$PYTHON")"

# ── 4. Server virtual environment ─────────────────────────────────────────────
header "4/6  Server Python environment (server/.venv)"
cd "$REPO_ROOT/server"
if [[ ! -d .venv ]]; then
    info "Creating server/.venv …"
    "$PYTHON" -m venv .venv
fi
source .venv/bin/activate
info "Upgrading pip …"
pip install --upgrade pip --quiet
info "Installing server dependencies …"
pip install -r requirements.txt --quiet
deactivate
success "Server environment ready."

# ── 5. Bot virtual environment ─────────────────────────────────────────────────
header "5/6  Bot bridge Python environment (bot/.venv)"
cd "$REPO_ROOT/bot"
if [[ ! -d .venv ]]; then
    info "Creating bot/.venv …"
    "$PYTHON" -m venv .venv
fi
source .venv/bin/activate
info "Upgrading pip …"
pip install --upgrade pip --quiet
info "Installing bot dependencies …"
pip install -r requirements.txt --quiet
deactivate
success "Bot environment ready."

# ── 6. Environment files ───────────────────────────────────────────────────────
header "6/6  Environment configuration"
cd "$REPO_ROOT"

if [[ ! -f server/.env ]]; then
    cat > server/.env << 'ENVEOF'
# ── AI Child Server — environment variables ──────────────────────────────────
# Get your key at https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-your-openai-api-key-here

# Optional: change the model (gpt-4o is the default)
# OPENAI_MODEL=gpt-4o

# SQLite database path (relative to server/)
DATABASE_URL=sqlite+aiosqlite:///./ai_child.db

# Server bind address
HOST=0.0.0.0
PORT=8000

# Autonomous research settings
RESEARCH_ENABLED=true
RESEARCH_QUERY_COUNT=3
RESEARCH_MAX_RESULTS=4

# Code sandbox timeout (seconds)
CODE_EXEC_TIMEOUT=10
ENVEOF
    warn "Created server/.env — please set your OPENAI_API_KEY before running."
else
    success "server/.env already exists."
fi

if [[ ! -f bot/.env ]]; then
    cat > bot/.env << 'ENVEOF'
# ── AI Child Bot Bridge — environment variables ───────────────────────────────
# URL of the running AI Child server
SERVER_URL=http://localhost:8000

# Telegram bot token from @BotFather (required for Telegram adapter)
TELEGRAM_TOKEN=your-telegram-bot-token-here

# Optional shared secret for the generic webhook bridge
# WEBHOOK_SECRET=change-me
ENVEOF
    warn "Created bot/.env — please set your TELEGRAM_TOKEN before running the bot."
else
    success "bot/.env already exists."
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}✅  Setup complete!${RESET}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit ${BOLD}server/.env${RESET} — set OPENAI_API_KEY"
echo "  2. Edit ${BOLD}bot/.env${RESET}    — set TELEGRAM_TOKEN (from @BotFather on Telegram)"
echo ""
echo "  3. Start the server (terminal 1):"
echo "     ${BOLD}make server${RESET}"
echo ""
echo "  4. Start the Telegram bot (terminal 2):"
echo "     ${BOLD}make bot${RESET}"
echo ""
echo "  5. Open Telegram and talk to your bot."
echo "     On first run the AI will ask you to give it a name!"
echo ""
echo "  Other commands:"
echo "     make test          — run all tests"
echo "     make dev           — run server + bot together"
echo "     make clean         — remove __pycache__ and .db files"
