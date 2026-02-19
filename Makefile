# ── Telegram File Storage Bot — Developer Commands ───────────────────────────
# Run `make help` to see all targets.

.PHONY: help setup run run-module docker-up docker-down docker-logs lint

PYTHON   := python3
VENV_DIR := .venv
VENV_BIN := $(VENV_DIR)/bin

help:
	@echo ""
	@echo "  make setup        Create venv and install dependencies"
	@echo "  make run          Run the bot locally (uses run.py)"
	@echo "  make run-module   Run the bot locally (uses -m bot.main)"
	@echo "  make docker-up    Build and start bot + MongoDB in Docker"
	@echo "  make docker-down  Stop Docker services"
	@echo "  make docker-logs  Tail bot logs from Docker"
	@echo ""

# ── Local development ─────────────────────────────────────────────────────────

setup:
	@echo "→ Creating virtual environment in $(VENV_DIR)/"
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -r requirements.txt
	@echo ""
	@echo "✅ Done. Activate with:  source $(VENV_DIR)/bin/activate"
	@echo "   Then copy .env.example → .env and fill in your values."

run: _check_env
	@echo "→ Starting bot via run.py …"
	@# PYTHONPATH is set here as a safety net in case the venv was activated
	@# from a different directory.
	PYTHONPATH=$(PWD) $(PYTHON) run.py

run-module: _check_env
	@echo "→ Starting bot via python -m bot.main …"
	PYTHONPATH=$(PWD) $(PYTHON) -m bot.main

_check_env:
	@test -f .env || (echo "❌  .env not found. Copy .env.example → .env first." && exit 1)

# ── Docker ────────────────────────────────────────────────────────────────────

docker-up: _check_env
	docker compose up --build -d
	@echo "✅ Services started. Logs: make docker-logs"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f bot
