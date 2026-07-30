# cowsay Makefile

HOST ?= 127.0.0.1
PORT ?= 8000
URL  := http://$(HOST):$(PORT)/ui/
ROOT := http://$(HOST):$(PORT)/
PY   := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
LOG  := /tmp/cowsay-uvicorn-$(PORT).log
OPEN := $(shell command -v open >/dev/null 2>&1 && echo open || echo xdg-open)

.PHONY: help ui dev

# Default target
help:
	@echo "Available commands:"
	@echo "  make ui    - Open the web UI (starts the server first if it isn't running)"
	@echo "  make dev   - Run the server in the foreground with reload"
	@echo ""
	@echo "Override host/port:  make ui PORT=8100"

# Open the web UI, starting the server first if needed.
ui:
	@if curl -s --max-time 2 $(ROOT) 2>/dev/null | grep -q '"status":"alive"'; then \
		echo "server already running at $(URL)"; \
	elif lsof -nP -iTCP:$(PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "ERROR: port $(PORT) is in use by another process (not cowsay):"; \
		lsof -nP -iTCP:$(PORT) -sTCP:LISTEN | tail -n +2 | awk '{print "  " $$1, "(pid " $$2 ")"}'; \
		echo "Try a different port:  make ui PORT=8100"; \
		exit 1; \
	else \
		[ -f .env ] || { echo "ERROR: .env not found. Run: cp .env.example .env"; exit 1; }; \
		echo "starting server on $(HOST):$(PORT)..."; \
		$(PY) -m uvicorn app.main:app --host $(HOST) --port $(PORT) --env-file .env > $(LOG) 2>&1 & \
		for i in $$(seq 1 40); do \
			curl -s --max-time 1 $(ROOT) 2>/dev/null | grep -q '"status":"alive"' && break; \
			sleep 0.25; \
		done; \
		curl -s --max-time 2 $(ROOT) 2>/dev/null | grep -q '"status":"alive"' || { \
			echo "ERROR: server failed to start. Last lines of $(LOG):"; \
			tail -5 $(LOG); \
			echo "(are postgres and redis up?  docker compose up -d postgres redis)"; \
			exit 1; \
		}; \
		echo "server started (log: $(LOG))"; \
	fi
	@echo "opening $(URL)"
	@$(OPEN) $(URL)

# Run the server in the foreground with auto-reload.
dev:
	@[ -f .env ] || { echo "ERROR: .env not found. Run: cp .env.example .env"; exit 1; }
	$(PY) -m uvicorn app.main:app --reload --host $(HOST) --port $(PORT) --env-file .env
