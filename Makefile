.PHONY: help install backend frontend agent dev stop test test-agent test-frontend test-all build check clean

.DEFAULT_GOAL := help

help: ## Show help for each Makefile target
	@echo "Available commands:"
	@echo "  make install       - Install frontend dependencies"
	@echo "  make backend       - Run the Python backend server (port 8080, loads .env)"
	@echo "  make frontend      - Run the Next.js frontend dev server (port 3000)"
	@echo "  make agent         - Check local Ollama availability and model configuration"
	@echo "  make dev           - Run both backend and frontend servers concurrently"
	@echo "  make stop          - Stop any running Atlas Fresh backend and frontend processes"
	@echo "  make test          - Run backend and assistant unit tests"
	@echo "  make test-agent    - Run assistant tests only"
	@echo "  make test-frontend - Run frontend validation/tests"
	@echo "  make test-all      - Run backend + agent + frontend checks"
	@echo "  make build         - Build the Next.js frontend for production"
	@echo "  make check         - Run full verification (tests + build)"
	@echo "  make clean         - Remove build artifacts and Python cache files"

install: ## Install frontend dependencies
	cd frontend && npm install

backend: ## Run Python API backend server (loads .env for Ollama config)
	@set -a; [ -f .env ] && . ./.env; set +a; python3 backend/server.py

frontend: ## Run Next.js frontend dev server
	cd frontend && npm run dev

agent: ## Check local Ollama availability (loads .env)
	@set -a; [ -f .env ] && . ./.env; set +a; python3 agent/check_ollama.py

stop: ## Stop any running Atlas Fresh backend (port 8080) and frontend (port 3000)
	@echo "Stopping Atlas Fresh services..."
	@BACKEND_PID=$$(lsof -t -nP -iTCP:8080 -sTCP:LISTEN 2>/dev/null); \
	if [ -n "$$BACKEND_PID" ]; then \
		echo "  Stopping backend PID $$BACKEND_PID (port 8080)..."; \
		kill $$BACKEND_PID 2>/dev/null && echo "  Backend stopped." || echo "  Backend already gone."; \
	else \
		echo "  No backend running on port 8080."; \
	fi
	@FRONTEND_PID=$$(lsof -t -nP -iTCP:3000 -sTCP:LISTEN 2>/dev/null); \
	if [ -n "$$FRONTEND_PID" ]; then \
		echo "  Stopping frontend PID $$FRONTEND_PID (port 3000)..."; \
		kill $$FRONTEND_PID 2>/dev/null && echo "  Frontend stopped." || echo "  Frontend already gone."; \
	else \
		echo "  No frontend running on port 3000."; \
	fi
	@sleep 1
	@echo "Done."

dev: ## Run both backend and frontend concurrently (loads .env, checks port conflicts)
	@echo "Checking for port conflicts..."
	@CONFLICT=0; \
	if lsof -nP -iTCP:8080 -sTCP:LISTEN > /dev/null 2>&1; then \
		echo ""; \
		echo "[ERROR] Port 8080 is already in use:"; \
		lsof -nP -iTCP:8080 -sTCP:LISTEN | tail -n +2 | awk '{print "  PID " $$2 ": " $$1}'; \
		CONFLICT=1; \
	fi; \
	if lsof -nP -iTCP:3000 -sTCP:LISTEN > /dev/null 2>&1; then \
		echo ""; \
		echo "[ERROR] Port 3000 is already in use:"; \
		lsof -nP -iTCP:3000 -sTCP:LISTEN | tail -n +2 | awk '{print "  PID " $$2 ": " $$1}'; \
		CONFLICT=1; \
	fi; \
	if [ "$$CONFLICT" = "1" ]; then \
		echo ""; \
		echo "  Run 'make stop' to stop all Atlas Fresh services, then retry."; \
		exit 1; \
	fi
	@echo "Starting backend and frontend..."
	$(MAKE) -j 2 backend frontend

test: ## Run backend and assistant unit tests
	PYTHONPATH=.:backend python3 -m unittest discover -s backend/tests

test-agent: ## Run assistant tests only
	PYTHONPATH=.:backend python3 -m unittest discover -s agent/tests

test-frontend: ## Run frontend validation
	@echo "Inspecting frontend package scripts..."
	@node -e 'const pkg = require("./frontend/package.json"); if (!pkg.scripts.test && !pkg.scripts.lint) { console.log("Frontend note: No unit test or lint script configured in frontend/package.json."); }'
	@echo "Validating frontend JavaScript syntax..."
	@node -c frontend/next.config.mjs
	@echo "Frontend validation: OK"

test-all: ## Run backend + agent + frontend checks
	@echo "=== Running Backend & Assistant Tests ==="
	$(MAKE) test
	@echo "\n=== Running Agent Tests ==="
	$(MAKE) test-agent
	@echo "\n=== Running Frontend Validation ==="
	$(MAKE) test-frontend
	@echo "\n[OK] All test suites completed successfully."

build: ## Build Next.js frontend
	cd frontend && npm run build

check: ## Run full verification
	@echo "=== Starting Full Project Verification ==="
	$(MAKE) test-all
	@echo "\n=== Building Production Frontend ==="
	$(MAKE) build
	@echo "\n[OK] Full project verification passed successfully."

clean: ## Clean build and cache files
	rm -rf frontend/.next
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
