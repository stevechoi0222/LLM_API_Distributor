# Environment Variables Configuration

This document lists all required and optional environment variables for the application.

## Application Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_NAME` | No | `GSE Visibility Engine` | Application name |
| `APP_VERSION` | No | `0.1.0` | Application version |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Database Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql+psycopg://geo:geo@localhost:5432/geo` | Database connection URL |
| `LOCAL_DATABASE_URL` | No | `postgresql+psycopg://geo:geo@postgres:5432/geo` | Local dev database URL |
| `DB_SCHEMA` | Yes | `geo_app` | PostgreSQL schema name |
| `DB_APPLY_MIGRATIONS` | No | `false` | Auto-apply migrations on startup (dev only) |
| `DB_COMPAT_MODE` | No | `false` | Use minimal 2-table schema for restricted environments |
| `USE_JSONB` | No | `true` | Use JSONB columns (else TEXT JSON) |
| `DB_POOL_SIZE` | No | `10` | Database connection pool size |
| `DB_MAX_OVERFLOW` | No | `20` | Max overflow connections |
| `DB_POOL_RECYCLE` | No | `1800` | Pool recycle time in seconds |

## Redis Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Redis connection URL |

## Celery Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CELERY_BROKER_URL` | Yes | `redis://localhost:6379/0` | Celery broker URL |
| `CELERY_RESULT_BACKEND` | Yes | `redis://localhost:6379/0` | Celery result backend URL |

## Security

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_KEYS` | Yes | `dev-key-123` | Comma-separated API keys for authentication |

## Provider API Keys

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Conditional | - | OpenAI API key (required if `ENABLE_OPENAI=true`) |
| `GOOGLE_API_KEY` | Conditional | - | Google/Gemini API key (required if `ENABLE_GEMINI=true`) (TKT-002) |
| `PERPLEXITY_API_KEY` | Conditional | - | Perplexity API key (required if `ENABLE_PERPLEXITY=true`) (TKT-002) |

## Provider Feature Flags (TKT-002)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENABLE_OPENAI` | No | `true` | Enable OpenAI provider |
| `ENABLE_GEMINI` | No | `false` | Enable Gemini provider (TKT-002: Full implementation with citations) |
| `ENABLE_PERPLEXITY` | No | `false` | Enable Perplexity provider (TKT-002: Full implementation with citations) |

**Note**: When a provider is disabled, any run attempt using that provider will be rejected with a validation error.

## Rate Limiting

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_RATE_LIMIT_QPS` | No | `5` | OpenAI queries per second limit |
| `OPENAI_RATE_LIMIT_BURST` | No | `10` | OpenAI burst limit |
| `GEMINI_RATE_LIMIT_QPS` | No | `3` | Gemini queries per second limit |
| `GEMINI_RATE_LIMIT_BURST` | No | `5` | Gemini burst limit |
| `PERPLEXITY_RATE_LIMIT_QPS` | No | `3` | Perplexity queries per second limit |
| `PERPLEXITY_RATE_LIMIT_BURST` | No | `5` | Perplexity burst limit |

## Provider Settings (Determinism)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEFAULT_TEMPERATURE` | No | `0.0` | Default temperature for deterministic responses |
| `DEFAULT_TOP_P` | No | `1.0` | Default top_p sampling parameter |
| `DEFAULT_MAX_TOKENS` | No | `1000` | Default maximum tokens in response |

## Cost Tracking

Prices in USD per 1,000 tokens:

### OpenAI

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_GPT4O_MINI_INPUT_PER_1K` | No | `0.15` | GPT-4o-mini input price |
| `OPENAI_GPT4O_MINI_OUTPUT_PER_1K` | No | `0.60` | GPT-4o-mini output price |
| `OPENAI_GPT4O_INPUT_PER_1K` | No | `2.50` | GPT-4o input price |
| `OPENAI_GPT4O_OUTPUT_PER_1K` | No | `10.00` | GPT-4o output price |

### Gemini (TKT-002)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_PRO_INPUT_PER_1K` | No | `0.125` | Gemini Pro input price |
| `GEMINI_PRO_OUTPUT_PER_1K` | No | `0.375` | Gemini Pro output price |
| `GEMINI_FLASH_INPUT_PER_1K` | No | `0.075` | Gemini Flash input price |
| `GEMINI_FLASH_OUTPUT_PER_1K` | No | `0.30` | Gemini Flash output price |

### Perplexity (TKT-002)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PERPLEXITY_SONAR_SMALL_INPUT_PER_1K` | No | `0.20` | Sonar Small input price |
| `PERPLEXITY_SONAR_SMALL_OUTPUT_PER_1K` | No | `0.20` | Sonar Small output price |
| `PERPLEXITY_SONAR_LARGE_INPUT_PER_1K` | No | `1.00` | Sonar Large input price |
| `PERPLEXITY_SONAR_LARGE_OUTPUT_PER_1K` | No | `1.00` | Sonar Large output price |

## Partner Delivery Configuration (TKT-001)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MAX_DELIVERY_ATTEMPTS` | No | `5` | Maximum retry attempts for partner deliveries |
| `DELIVERY_RETRY_BACKOFF_BASE` | No | `2` | Exponential backoff base (delay = base^attempt) |
| `DELIVERY_TIMEOUT` | No | `15.0` | Partner API request timeout in seconds |
| `PARTNER_WEBHOOK_URL` | No | `http://mock-partner.local/webhook` | Default partner webhook URL |
| `PARTNER_WEBHOOK_HEADERS_JSON` | No | `{}` | Partner webhook headers as JSON string |

### Partner Webhook Headers Example

To add custom headers to partner webhook deliveries:

```bash
PARTNER_WEBHOOK_HEADERS_JSON='{"Authorization": "Bearer token123", "X-Partner-ID": "partner456"}'
```

These headers will be merged with default headers (`Content-Type: application/json`) when making delivery requests.

### Per-Export Configuration

Individual exports can override the default webhook URL and headers by providing them in the `config` field when creating an export:

```json
{
  "run_id": "run_123",
  "format": "jsonl",
  "mapper_name": "example_partner",
  "mapper_version": "v1",
  "config": {
    "webhook_url": "https://custom-partner.com/webhook",
    "headers": {
      "Authorization": "Bearer custom-token"
    }
  }
}
```

## Example .env File

```bash
# Application
APP_NAME=GSE Visibility Engine
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+psycopg://geo:geo@postgres:5432/geo
DB_SCHEMA=geo_app
DB_APPLY_MIGRATIONS=true
USE_JSONB=true

# Redis & Celery
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Security
API_KEYS=dev-key-123,prod-key-456

# Providers
OPENAI_API_KEY=sk-your-openai-key-here
ENABLE_OPENAI=true
ENABLE_GEMINI=false
ENABLE_PERPLEXITY=false

# Delivery
MAX_DELIVERY_ATTEMPTS=5
DELIVERY_RETRY_BACKOFF_BASE=2
DELIVERY_TIMEOUT=15.0
PARTNER_WEBHOOK_URL=http://mock-partner.local/webhook
PARTNER_WEBHOOK_HEADERS_JSON={}
```

## Enabling Gemini and Perplexity Providers (TKT-002)

To enable Gemini and/or Perplexity providers:

### Enable Gemini

```bash
# Set feature flag
ENABLE_GEMINI=true

# Provide API key
GOOGLE_API_KEY=your-google-api-key-here

# Optional: Adjust rate limits
GEMINI_RATE_LIMIT_QPS=3
GEMINI_RATE_LIMIT_BURST=5

# Optional: Adjust pricing
GEMINI_PRO_INPUT_PER_1K=0.125
GEMINI_PRO_OUTPUT_PER_1K=0.375
```

### Enable Perplexity

```bash
# Set feature flag
ENABLE_PERPLEXITY=true

# Provide API key
PERPLEXITY_API_KEY=your-perplexity-api-key-here

# Optional: Adjust rate limits
PERPLEXITY_RATE_LIMIT_QPS=3
PERPLEXITY_RATE_LIMIT_BURST=5

# Optional: Adjust pricing
PERPLEXITY_SONAR_SMALL_INPUT_PER_1K=0.20
PERPLEXITY_SONAR_SMALL_OUTPUT_PER_1K=0.20
```

### Using in Runs

Once enabled, you can use these providers in run configurations:

```json
{
  "campaign_id": "campaign_123",
  "providers": [
    {"name": "openai", "model": "gpt-4o-mini"},
    {"name": "gemini", "model": "gemini-1.5-pro"},
    {"name": "perplexity", "model": "llama-3.1-sonar-small-128k-online"}
  ]
}
```

**Note**: If you attempt to use a disabled provider, the API will return a 400/422 validation error.

### Citations Handling

Both Gemini and Perplexity automatically extract and normalize citations:

- **Gemini**: Extracts citations from grounding metadata and JSON response
- **Perplexity**: Extracts citations from provider-native fields and JSON response
- All citations are validated (http/https only) and deduplicated
- Citations are stored in `responses.citations_json`

## Development vs Production

### Development
- `DB_APPLY_MIGRATIONS=true` - Auto-apply migrations
- `LOG_LEVEL=DEBUG` - Verbose logging
- `PARTNER_WEBHOOK_URL=http://mock-partner.local/webhook` - Mock endpoint

### Staging/Production
- `DB_APPLY_MIGRATIONS=false` - Manual migration management
- `LOG_LEVEL=INFO` or `WARNING` - Reduced logging
- `PARTNER_WEBHOOK_URL=https://real-partner.com/webhook` - Real endpoint
- Apply migrations manually using SQL from `artefacts/migrations.sql`


