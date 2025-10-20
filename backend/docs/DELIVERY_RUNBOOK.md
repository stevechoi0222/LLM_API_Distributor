# Delivery Queue & Webhook System (TKT-001)

## Quick Demo

Get started with a complete end-to-end demo in minutes:

### Prerequisites

1. **Set environment variables** (`.env` in `backend/` directory):
   ```bash
   DATABASE_URL=postgresql+psycopg://geo:geo@postgres:5432/geo
   REDIS_URL=redis://redis:6379/0
   API_KEY=change_me
   DB_SCHEMA=geo_app
   DB_APPLY_MIGRATIONS=true
   USE_JSONB=true
   ENABLE_OPENAI=true
   OPENAI_API_KEY=sk-your-openai-key-here
   ```

2. **Install dependencies**:
   - Docker & Docker Compose
   - `jq` (JSON processor for bash)

### Run OpenAI Demo

From the project root:

```bash
# 1. Start the stack (Postgres, Redis, API, Celery workers)
make up

# 2. In a new terminal, run the demo
make demo-openai
```

**What it does**:
1. Imports 2 sample questions about battery life
2. Creates a run with OpenAI (gpt-4o-mini, temperature=0)
3. Executes the run and polls for completion
4. Exports results to XLSX using `user_excel_v0_1` mapper
5. Prints the output file path

**Output**: `backend/artefacts/user_excel_v0_1_{run_id}.xlsx`

The XLSX contains:
- **AI_API_04_QUERY** sheet: Query results with provider/model/response/cost
- **AI_API_08_CITATION** sheet: Extracted citations with URLs

### Run Multi-Provider Demo (Optional)

For testing with OpenAI, Gemini, and Perplexity:

1. **Enable providers in `.env`**:
   ```bash
   ENABLE_GEMINI=true
   ENABLE_PERPLEXITY=true
   GOOGLE_API_KEY=your-google-key
   PERPLEXITY_API_KEY=your-perplexity-key
   ```

2. **Restart stack**:
   ```bash
   make down
   make up
   ```

3. **Run multi-provider demo**:
   ```bash
   make demo-multi
   ```

This creates a run with 3 providers and exports a single XLSX with results from all providers (separate rows per provider).

### Troubleshooting

- **API not healthy**: Wait 10-15 seconds after `make up` for services to initialize
- **Import fails**: Check that `backend/samples/import.json` exists
- **Run stuck in pending**: Check Celery worker logs: `docker compose logs celery`
- **Export missing file_url**: Check API logs: `docker compose logs api`

## Overview

The delivery queue system decouples partner API delivery from LLM run execution. After generating results, the system:

1. Creates export records with optional mapper configuration
2. Generates delivery payloads via configurable mappers
3. Enqueues delivery tasks to Celery workers
4. POSTs payloads to partner webhooks with retry logic
5. Tracks delivery status and audit trail

## Architecture

```
Run Results → Export Service → Mapper → Deliveries → Celery Worker → Partner API
                                                             ↓
                                                     Retry with backoff
                                                     (5xx/network errors)
```

## Key Features

- **Deterministic mapping**: Versioned mappers (v1, v2, etc.) for schema evolution
- **Reliable delivery**: Exponential backoff + jitter for 5xx/network errors
- **No unnecessary retries**: 4xx errors mark delivery as failed immediately
- **Audit trail**: Full request/response logging with attempt tracking
- **Rate limiting**: Per-partner rate limiting using Redis token buckets
- **Configurable**: Per-export webhook URL and headers

## Database Schema

### Deliveries Table (`geo_app.deliveries`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `export_id` | UUID | Reference to exports table |
| `run_id` | TEXT | Denormalized for queries |
| `mapper_name` | TEXT | Mapper identifier (e.g., "example_partner") |
| `mapper_version` | TEXT | Mapper version (e.g., "v1") |
| `payload_json` | JSONB/TEXT | Exact payload sent to partner |
| `status` | TEXT | `pending`, `succeeded`, `failed` |
| `attempts` | INT | Number of delivery attempts |
| `last_error` | TEXT | Most recent error message |
| `response_body` | TEXT | Partner API response (truncated to 5000 chars) |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update timestamp |

## API Endpoints

### POST /api/v1/exports

Create export job with optional mapper for partner delivery.

**Request:**
```json
{
  "run_id": "run_123",
  "format": "jsonl",
  "mapper_name": "example_partner",
  "mapper_version": "v1",
  "config": {
    "webhook_url": "https://partner.com/webhook",
    "headers": {
      "Authorization": "Bearer token123"
    }
  }
}
```

**Response:**
```json
{
  "id": "export_456",
  "run_id": "run_123",
  "format": "jsonl",
  "mapper_name": "example_partner",
  "mapper_version": "v1",
  "status": "pending",
  "file_url": null,
  "created_at": "2024-10-20T12:00:00Z",
  "deliveries_created": 42
}
```

### GET /api/v1/exports/{export_id}

Get export status with delivery statistics and sample failures.

**Response:**
```json
{
  "id": "export_456",
  "run_id": "run_123",
  "format": "jsonl",
  "mapper_name": "example_partner",
  "mapper_version": "v1",
  "status": "completed",
  "file_url": "artefacts/run_123_export_456.jsonl",
  "created_at": "2024-10-20T12:00:00Z",
  "delivery_stats": {
    "pending": 5,
    "succeeded": 35,
    "failed": 2
  },
  "sample_failures": [
    {
      "id": "delivery_789",
      "last_error": "HTTP 400: Invalid payload",
      "attempts": 1,
      "updated_at": "2024-10-20T12:05:00Z"
    }
  ]
}
```

### GET /api/v1/deliveries/{delivery_id}

Get individual delivery status.

**Response:**
```json
{
  "id": "delivery_789",
  "export_id": "export_456",
  "run_id": "run_123",
  "mapper_name": "example_partner",
  "mapper_version": "v1",
  "status": "succeeded",
  "attempts": 2,
  "last_error": null,
  "response_body": "{\"success\": true, \"id\": \"partner_123\"}",
  "created_at": "2024-10-20T12:00:00Z",
  "updated_at": "2024-10-20T12:02:00Z"
}
```

## Delivery Behavior

### Success (2xx)
- Status → `succeeded`
- Store `response_body` (truncated if large)
- No retry

### Client Error (4xx)
- Status → `failed`
- Store `last_error` and `response_body`
- **No retry** (client errors are not transient)

### Server Error (5xx) or Network Error
- Status remains `pending`
- Store `last_error`
- **Retry with exponential backoff + jitter**
- After max attempts → status becomes `failed`

### Retry Strategy

```python
delay = min(base^attempt ± 20% jitter, 60 seconds)
```

Example with `base=2`:
- Attempt 1: ~2s
- Attempt 2: ~4s
- Attempt 3: ~8s
- Attempt 4: ~16s
- Attempt 5: ~32s (capped at 60s)

### Rate Limiting

Each mapper has its own rate limit bucket:
- Bucket name: `partner_delivery_{mapper_name}`
- Uses Redis token bucket algorithm
- Configurable QPS per partner

## Configuration

### Environment Variables

```bash
# Delivery settings
MAX_DELIVERY_ATTEMPTS=5
DELIVERY_RETRY_BACKOFF_BASE=2
DELIVERY_TIMEOUT=15.0

# Default partner webhook
PARTNER_WEBHOOK_URL=https://partner.com/webhook
PARTNER_WEBHOOK_HEADERS_JSON='{"Authorization": "Bearer token"}'
```

### Per-Export Configuration

Override default settings via `config` in POST /api/v1/exports:

```json
{
  "webhook_url": "https://custom.partner.com/webhook",
  "headers": {
    "Authorization": "Bearer custom-token",
    "X-Custom-Header": "value"
  }
}
```

## Mappers

### Creating a Mapper

Mappers transform normalized run results to partner-specific schemas.

**Example Mapper (`app/exporters/mappers/example_webhook.py`):**

```python
from app.exporters.mappers.base import BaseMapper

class ExampleWebhookMapperV1(BaseMapper):
    version = "v1"
    
    def map(self, result: dict) -> dict:
        """Transform result to partner schema."""
        return {
            "query_id": result["run_item_id"],
            "question": result["question_text"],
            "answer": result["response"]["answer"],
            "sources": result["response"]["citations"],
            "metadata": {
                "provider": result["provider"],
                "model": result["model"],
                "cost_usd": result["cost_cents"] / 100,
            }
        }
```

**Register Mapper:**

```python
MAPPER_REGISTRY = {
    "example_partner": {
        "v1": ExampleWebhookMapperV1(),
        "v2": ExampleWebhookMapperV2(),  # Future version
    }
}
```

### Mapper Versioning

- Use semantic versions: `v1`, `v2`, etc.
- Keep old versions for historical exports
- Default to latest stable version

## Monitoring & Troubleshooting

### Check Delivery Status

```bash
curl -H "x-api-key: your-key" \
  http://localhost:8000/api/v1/exports/{export_id}
```

### Query Failed Deliveries

```sql
SELECT id, run_id, mapper_name, last_error, attempts, updated_at
FROM geo_app.deliveries
WHERE status = 'failed'
ORDER BY updated_at DESC
LIMIT 10;
```

### Retry Failed Delivery Manually

```python
from app.workers.tasks import deliver_to_partner

# Re-enqueue delivery
deliver_to_partner.delay("delivery_id")
```

### Common Issues

#### All Deliveries Failing with 401

**Cause:** Invalid or expired authentication token

**Solution:** Update `PARTNER_WEBHOOK_HEADERS_JSON` with fresh token

```bash
PARTNER_WEBHOOK_HEADERS_JSON='{"Authorization": "Bearer new-token"}'
```

#### Deliveries Stuck in Pending

**Cause:** Celery worker not running or Redis connection issue

**Solution:** Check worker logs and Redis connectivity

```bash
# Check Celery workers
celery -A app.workers.celery_app inspect active

# Check Redis
redis-cli -h redis ping
```

#### Rate Limit Exceeded

**Cause:** Partner QPS limit exceeded

**Solution:** Adjust rate limit or slow down delivery

```python
from app.core.rate_limit import get_rate_limiter

rate_limiter = get_rate_limiter()
# Increase bucket capacity or reduce QPS
```

## Testing

### Unit Tests

```bash
pytest tests/test_unit/test_delivery_worker.py -v
```

Tests cover:
- Success (2xx) response handling
- Client error (4xx) no-retry behavior
- Server error (5xx) retry logic
- Network timeout/error retry
- Max attempts exhaustion
- Custom headers
- Rate limiting

### Integration Tests

```bash
pytest tests/test_integration/test_export_delivery_workflow.py -v
```

Tests cover:
- End-to-end export + delivery workflow
- Multiple retry attempts
- Delivery stats aggregation
- Sample failures retrieval

### Manual Testing

```bash
# 1. Create export with mapper
curl -X POST http://localhost:8000/api/v1/exports \
  -H "x-api-key: dev-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "run_123",
    "format": "jsonl",
    "mapper_name": "example_partner",
    "mapper_version": "v1",
    "config": {
      "webhook_url": "http://httpbin.org/post"
    }
  }'

# 2. Check export status
curl http://localhost:8000/api/v1/exports/{export_id} \
  -H "x-api-key: dev-key-123"

# 3. Check individual delivery
curl http://localhost:8000/api/v1/deliveries/{delivery_id} \
  -H "x-api-key: dev-key-123"
```

## Migration

### Staging/Production Migration

```bash
# Apply SQL migration
psql $DATABASE_URL -f artefacts/migrations.sql
```

The migration adds `mapper_version` column to `deliveries` table.

### Rollback

```sql
BEGIN;
ALTER TABLE geo_app.deliveries DROP COLUMN mapper_version;
COMMIT;
```

## Performance Considerations

### Batch Deliveries

For large exports (1000+ results), deliveries are created and enqueued incrementally to avoid memory issues.

### Celery Concurrency

Adjust worker concurrency based on partner rate limits:

```bash
# Start with 10 concurrent workers per partner
celery -A app.workers.celery_app worker \
  --concurrency=10 \
  --queue=deliveries
```

### Database Indexes

Existing indexes on `deliveries`:
- `ix_deliveries_export_id`
- `ix_deliveries_status`
- `ix_deliveries_run_id`

## Security

- API keys required for all endpoints
- Partner credentials stored in environment variables (not database)
- Response bodies truncated to prevent memory exhaustion
- No DB locks used (uses row-level updates)

## Export to user_excel_v0_1 Format (TKT-013)

The `user_excel_v0_1` mapper exports run results to a multi-sheet XLSX format with exact column specifications.

### Usage

```bash
curl -X POST http://localhost:8000/api/v1/exports \
  -H "x-api-key: dev-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "run_123",
    "format": "xlsx",
    "mapper_name": "user_excel_v0_1",
    "mapper_version": "v1"
  }'
```

### Output Format

Creates `artefacts/user_excel_v0_1_{run_id}.xlsx` with two sheets:

**Sheet: AI_API_04_QUERY**
- One row per (provider × question) combination
- Columns: campaign, run_id, question_id, persona_name, question_text, provider, model, response_text, latency_ms, prompt_tokens, completion_tokens, cost_cents, status

**Sheet: AI_API_08_CITATION**
- One row per citation URL
- Columns: run_id, question_id, provider, citation_index (0-based), citation_url

### Features

- **Multi-provider support**: Includes separate rows for each provider (OpenAI, Gemini, Perplexity)
- **Citations normalization**: Extracts from `responses.citations_json`
- **URL validation**: Only includes http/https URLs
- **Truncation**: Long cells truncated to 10K chars
- **Exact headers**: Column order matches specification

### Example

```bash
# 1. Create export
EXPORT_ID=$(curl -X POST http://localhost:8000/api/v1/exports \
  -H "x-api-key: dev-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "run_abc123",
    "format": "xlsx",
    "mapper_name": "user_excel_v0_1",
    "mapper_version": "v1"
  }' | jq -r '.id')

# 2. Check export status
curl http://localhost:8000/api/v1/exports/$EXPORT_ID \
  -H "x-api-key: dev-key-123"

# 3. File location
# artefacts/user_excel_v0_1_run_abc123.xlsx
```

## Future Enhancements

- [ ] Webhook signature verification (HMAC)
- [ ] Delivery batching (multiple results per webhook call)
- [ ] Delivery scheduling (delayed/scheduled deliveries)
- [ ] Dead letter queue for permanently failed deliveries
- [ ] Prometheus metrics for delivery monitoring


