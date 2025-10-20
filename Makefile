# Makefile for LLM API Distributor

.PHONY: help up down logs demo-openai demo-multi clean

help: ## Show this help message
	@echo "Available targets:"
	@echo "  up           - Start Docker Compose stack (build)"
	@echo "  down         - Stop and remove Docker Compose stack"
	@echo "  logs         - Tail Docker Compose logs"
	@echo "  demo-openai  - Run OpenAI-only demo (end-to-end)"
	@echo "  demo-multi   - Run multi-provider demo (OpenAI+Gemini+Perplexity)"
	@echo "  clean        - Clean up artefacts and temporary files"

up: ## Start Docker Compose stack
	cd backend && docker compose up --build

down: ## Stop Docker Compose stack
	cd backend && docker compose down -v

logs: ## Tail Docker Compose logs
	cd backend && docker compose logs -f

demo-openai: ## Run OpenAI demo
	cd backend && bash scripts/demo_openai.sh

demo-multi: ## Run multi-provider demo
	cd backend && bash scripts/demo_multi.sh

clean: ## Clean up generated files
	rm -f backend/artefacts/*.xlsx
	rm -f backend/artefacts/*.csv
	rm -f backend/artefacts/*.jsonl
	rm -rf backend/htmlcov
	rm -rf backend/.pytest_cache
	@echo "Cleaned up artefacts and cache files"

