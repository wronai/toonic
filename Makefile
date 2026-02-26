.PHONY: help install install-all install-dev test lint server client shell docker docker-up docker-down clean docs

PYTHON  := .venv/bin/python
PIP     := .venv/bin/pip
PYTEST  := .venv/bin/pytest
PORT    ?= $(if $(TOONIC_PORT),$(TOONIC_PORT),8900)

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────

venv: ## Create virtual environment
	python3 -m venv .venv
	$(PIP) install --upgrade pip

install: venv ## Install core package
	$(PIP) install -e .

install-dev: venv ## Install with dev + server deps
	$(PIP) install -e ".[dev,server]"

install-all: venv ## Install everything (video, audio, llm, server)
	$(PIP) install -e ".[all]"

install-llm: ## Install LLM dependencies (litellm)
	$(PIP) install litellm

# ── Testing ───────────────────────────────────────────────────

test: ## Run all tests
	$(PYTEST) tests/ -v

test-server: ## Run server tests only
	$(PYTEST) tests/test_server.py -v

test-cov: ## Run tests with coverage
	$(PYTEST) tests/ -v --cov=toonic --cov-report=html

# ── Server ────────────────────────────────────────────────────

server: ## Start Toonic Server (web UI on :8900)
	$(PYTHON) -m toonic.server --port $(PORT)

server-code: ## Analyze code example
	$(PYTHON) -m toonic.server \
		--source file:./examples/code-analysis/sample-project/ \
		--port $(PORT) \
		--goal "find bugs, security issues, suggest improvements" \
		--interval 0

server-logs: ## Monitor log example
	$(PYTHON) -m toonic.server \
		--source log:./docker/test-data/sample.logfile \
		--port $(PORT) \
		--goal "monitor logs, detect errors" \
		--interval 10

server-camera: ## Connect real RTSP camera
	$(PYTHON) -m toonic.server \
		--source "rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main" \
		--port $(PORT) \
		--goal "monitor video stream, detect changes" \
		--interval 15

server-multi: ## Multi-source (code + logs + camera)
	$(PYTHON) -m toonic.server \
		--source file:./examples/code-analysis/sample-project/ \
		--source log:./docker/test-data/sample.logfile \
		--source "rtsp://admin:123456@192.168.188.146:554/h264Preview_01_main" \
		--port $(PORT) \
		--goal "comprehensive analysis: code + logs + video" \
		--interval 30

client: ## Start CLI shell client
	$(PYTHON) -m toonic.server.client

status: ## Show server status
	$(PYTHON) -m toonic.server.client --status

# ── Docker ────────────────────────────────────────────────────

docker-build: ## Build Docker image
	docker compose -f docker/docker-compose.yml build

docker-up: ## Start Docker stack (RTSP + server)
	docker compose -f docker/docker-compose.yml up -d

docker-down: ## Stop Docker stack
	docker compose -f docker/docker-compose.yml down

docker-logs: ## Show Docker logs
	docker compose -f docker/docker-compose.yml logs -f toonic-server

docker-streams: ## Start only RTSP test streams
	docker compose -f docker/docker-compose.yml up -d rtsp-server test-stream-video test-stream-cam2 test-stream-audio

# ── Conversion ────────────────────────────────────────────────

convert: ## Convert file: make convert FILE=./main.py FMT=toon
	$(PYTHON) -m toonic spec $(FILE) --format $(FMT)

batch: ## Batch convert directory: make batch DIR=./src/
	$(PYTHON) -m toonic batch $(DIR)

# ── Cleanup ───────────────────────────────────────────────────

clean: ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

clean-docker: ## Remove Docker volumes and images
	docker compose -f docker/docker-compose.yml down -v --rmi local
