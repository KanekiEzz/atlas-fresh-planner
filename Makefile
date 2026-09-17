.PHONY: help install backend frontend test dev build clean

# Default target
.DEFAULT_GOAL := help

help: ## Show help for each Makefile target
	@echo "Available commands:"
	@echo "  make install   - Install frontend dependencies"
	@echo "  make backend   - Run the Python backend server (port 8080)"
	@echo "  make frontend  - Run the Next.js frontend dev server (port 3000)"
	@echo "  make dev       - Run both backend and frontend servers concurrently"
	@echo "  make test      - Run backend unit tests"
	@echo "  make build     - Build the Next.js frontend for production"
	@echo "  make clean     - Remove build artifacts and Python cache files"

install: ## Install frontend dependencies
	cd frontend && npm install

backend: ## Run Python API backend server
	python3 backend/server.py

frontend: ## Run Next.js frontend dev server
	cd frontend && npm run dev

dev: ## Run both backend and frontend concurrently
	@echo "Starting backend and frontend..."
	$(MAKE) -j 2 backend frontend

test: ## Run backend unit tests
	PYTHONPATH=backend python3 -m unittest discover -s backend/tests

build: ## Build Next.js frontend
	cd frontend && npm run build

clean: ## Clean build and cache files
	rm -rf frontend/.next
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
