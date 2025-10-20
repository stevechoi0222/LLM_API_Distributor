# GSE Visibility Engine

Marketing/visibility engine for Generative Search Engines (ChatGPT, Gemini, Perplexity).

## Overview

Execute questions against GSE provider APIs, track responses/citations/metrics, and export results with support for:
- External managed PostgreSQL (no superuser required)
- Redis-based concurrency control and rate limiting
- Celery workers for async processing
- Multi-format exports (CSV, XLSX, JSONL)
- Partner API delivery with retries

## Quick Start (Local Development)

```bash
# Copy environment file
cp .env.example .env

# Edit .env with your API keys
# For local dev, set DB_APPLY_MIGRATIONS=true

# Start all services
docker-compose up -d

# Check health
curl http://localhost:8000/healthz

# Run tests
docker-compose exec api pytest
```

## Architecture

- **FastAPI** - Async REST API
- **PostgreSQL** - Data storage (external managed in prod)
- **Redis** - Rate limiting, idempotency, Celery broker
- **Celery** - Worker tasks for provider calls and exports
- **SQLAlchemy** - Async ORM with schema-aware migrations

## Database Modes

### Normal Mode (full schema)
All tables under `geo_app` schema: campaigns, topics, personas, questions, runs, run_items, responses, exports, files, deliveries.

### Compat Mode
Minimal 2-table schema (`events`, `results`) for restricted environments where DDL changes are heavily controlled.

Set `DB_COMPAT_MODE=true` to enable.

## Migrations

### Local Development
Migrations auto-apply on startup when `DB_APPLY_MIGRATIONS=true`.

### Production/Staging
Generate offline SQL for DBA handoff:
```bash
./scripts/migrations_offline.sh
```
This creates `artefacts/migrations.sql` for manual application.

## API Endpoints

### Ingestion
- `POST /api/v1/questions:ingest` - Upload Excel/CSV
- `POST /api/v1/question-sets:import` - Import from agent (JSONL/JSON)

### Runs
- `POST /api/v1/runs` - Create run
- `POST /api/v1/runs/{id}/start` - Start execution
- `GET /api/v1/runs/{id}` - Status and cost summary
- `GET /api/v1/runs/{id}/items` - Paginated results
- `POST /api/v1/runs/{id}/resume` - Resume failed items

### Exports
- `GET /api/v1/runs/{id}/results:download?format=csv|xlsx|jsonl` - Download
- `POST /api/v1/exports` - Create export job with mapper
- `GET /api/v1/exports/{id}` - Export status

### Campaigns
- `POST /api/v1/campaigns` - Create campaign
- `POST /api/v1/campaigns/{id}/topics` - Add topics
- `POST /api/v1/personas` - Create personas

### Health
- `GET /healthz` - Health check (DB + Redis)

## Authentication

API key required in header:
```
x-api-key: your-api-key-here
```

## Provider Support

- **OpenAI** - Enabled (`ENABLE_OPENAI=true`)
- **Gemini** - Stub, disabled by default
- **Perplexity** - Stub, disabled by default

## Cost Tracking

Token usage automatically converted to cost (USD cents) based on configured pricing.
View aggregated costs at run level via `GET /api/v1/runs/{id}`.

## Documentation

- [DB Handoff Guide](../docs/DB_HANDOFF.md) - Migration process for external DB
- [API Documentation](http://localhost:8000/docs) - Swagger UI when running

## License

Proprietary


