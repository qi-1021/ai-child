# AI Child — developer convenience commands
# Requires: bash setup_mac.sh (first time) or manual venv creation
.PHONY: setup-mac server bot dev test test-server test-bot clean clean-deps

# ── Setup ─────────────────────────────────────────────────────────────────────

setup-mac:
	@bash setup_mac.sh

# ── Run ───────────────────────────────────────────────────────────────────────

## Start the AI Child server (requires server/.env with OPENAI_API_KEY)
server:
	cd server && .venv/bin/python main.py

## Start the bot bridge (requires bot/.env with TELEGRAM_TOKEN)
bot:
	cd bot && .venv/bin/python main.py

## Run server + bot together (Ctrl-C stops both)
dev:
	@trap 'kill %1 %2 2>/dev/null; exit' INT TERM; \
	 (cd server && .venv/bin/python main.py) & \
	 (cd bot   && .venv/bin/python main.py) & \
	 wait

# ── Test ──────────────────────────────────────────────────────────────────────

test: test-server test-bot

test-server:
	cd server && .venv/bin/python -m pytest tests/ -v --asyncio-mode=auto

test-bot:
	cd bot && .venv/bin/python -m pytest tests/ -v --asyncio-mode=auto

# ── Clean ─────────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

## !! Also deletes the AI's memory database — use with care
clean-all: clean
	find . -name "*.db" -not -path "./.git/*" -delete 2>/dev/null || true
	find . -name "*.db-shm" -o -name "*.db-wal" -delete 2>/dev/null || true

## Remove virtual environments (run setup-mac again afterwards)
clean-deps:
	rm -rf server/.venv bot/.venv
