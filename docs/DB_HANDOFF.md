# Database Handoff Guide

## Overview

This application works with an **externally-managed PostgreSQL database** where we do not have superuser privileges. All database schema changes must be reviewed and applied by your DBA team.

## Key Constraints

- **No superuser access** - We cannot create extensions or roles
- **Schema-scoped** - All tables under `geo_app` schema (configurable via `DB_SCHEMA`)
- **No DB locks** - Redis handles all concurrency, idempotency, and rate-limiting
- **No extensions required** - UUIDs generated app-side, JSONB optional

## Migration Workflow

### Local Development

In local development, migrations can auto-apply:

```bash
export DB_APPLY_MIGRATIONS=true
docker-compose up
```

The application will run `alembic upgrade head` on startup.

### Production/Staging

**Never auto-apply migrations** in production/staging. Instead:

1. **Generate offline SQL**:
   ```bash
   cd backend
   ./scripts/migrations_offline.sh
   ```

   This creates `artefacts/migrations.sql` with idempotent DDL.

2. **Review SQL** - Check the generated SQL for:
   - `CREATE SCHEMA IF NOT EXISTS geo_app`
   - `CREATE TABLE IF NOT EXISTS ...`
   - `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...`
   - No `DROP` statements (unless explicitly required)

3. **Hand off to DBA** - Provide `artefacts/migrations.sql` to your DBA team with these notes:
   - SQL is idempotent (safe to run multiple times)
   - All objects are under `geo_app` schema
   - No extensions required
   - Script includes both up and down migrations

4. **DBA applies SQL** in staging, then production

5. **Deploy application** with `DB_APPLY_MIGRATIONS=false` (default)

## Required Database Privileges

The application requires a **read/write role** with:

```sql
-- Grant schema access
GRANT USAGE ON SCHEMA geo_app TO your_app_role;

-- Grant table permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA geo_app TO your_app_role;
GRANT SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA geo_app TO your_app_role;

-- Future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA geo_app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO your_app_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA geo_app GRANT SELECT, UPDATE ON SEQUENCES TO your_app_role;
```

**No role creation, extension installation, or superuser privileges required.**

## Connection Configuration

### Production/Staging

```bash
DATABASE_URL=postgresql+psycopg://your_app_role:password@prod-db.example.com:5432/prod_db
DB_SCHEMA=geo_app
DB_APPLY_MIGRATIONS=false
```

### Local Development

```bash
DATABASE_URL=postgresql+psycopg://geo:geo@localhost:5432/geo
DB_SCHEMA=geo_app
DB_APPLY_MIGRATIONS=true
```

## Schema Overview

### Normal Mode (Full Schema)

**Tables under `geo_app` schema:**

- `campaigns` - Top-level campaigns
- `topics` - Topics within campaigns
- `personas` - User personas for questions
- `questions` - Questions paired with topics and personas
- `runs` - Execution runs
- `run_items` - Individual question executions
- `responses` - Provider responses with costs
- `exports` - Export jobs
- `deliveries` - Outbound partner API deliveries
- `files` - Uploaded file metadata

**Key indexes:**
- `UNIQUE (run_items.idempotency_key)`
- Indexes on foreign keys and status columns
- GIN indexes on JSON columns (if `USE_JSONB=true`)

### Compat Mode (Minimal Schema)

If DDL is heavily restricted, use **compat mode** with only 2 tables:

```sql
-- geo_app.events
CREATE TABLE geo_app.events (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload TEXT NOT NULL
);

-- geo_app.results
CREATE TABLE geo_app.results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    item_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    response TEXT,
    meta TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_results_run_id ON geo_app.results (run_id);
CREATE INDEX idx_results_item_id ON geo_app.results (item_id);
```

Enable with:
```bash
DB_COMPAT_MODE=true
```

The application writes normalized records as JSON strings in `payload`/`meta` fields. Exporters reconstruct data from these.

## JSONB vs TEXT JSON

By default, JSON columns use `JSONB` (PostgreSQL native):

```bash
USE_JSONB=true
```

If your DB version doesn't support JSONB, fall back to `TEXT`:

```bash
USE_JSONB=false
```

The application handles serialization/deserialization automatically.

## Search Path

The application sets `search_path` on every connection:

```sql
SET search_path TO geo_app, public;
```

This allows unqualified table names to resolve to `geo_app.*` while still accessing `public` for built-in types.

## Migration Script Details

### scripts/migrations_offline.sh

```bash
#!/bin/bash
set -e

mkdir -p artefacts
export DB_SCHEMA=${DB_SCHEMA:-geo_app}
alembic upgrade head --sql > artefacts/migrations.sql

echo "✓ Generated artefacts/migrations.sql"
echo "  Schema: $DB_SCHEMA"
```

### Example Generated SQL

```sql
-- Create schema
CREATE SCHEMA IF NOT EXISTS geo_app;

-- Create campaigns table
CREATE TABLE IF NOT EXISTS geo_app.campaigns (
    id TEXT NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    product_name VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

-- Add column (idempotent)
ALTER TABLE geo_app.run_items ADD COLUMN IF NOT EXISTS cost_cents NUMERIC(12,2);
```

## Troubleshooting

### Connection Issues

**Error:** `permission denied for schema geo_app`

**Solution:** DBA must grant `USAGE` on schema:
```sql
GRANT USAGE ON SCHEMA geo_app TO your_app_role;
```

**Error:** `relation "geo_app.campaigns" does not exist`

**Solution:** Migrations not applied. Hand `artefacts/migrations.sql` to DBA.

### Migration Generation

**Error:** `alembic: command not found`

**Solution:** Install dependencies:
```bash
cd backend
poetry install
```

**Error:** `Can't locate revision identified by 'head'`

**Solution:** Initialize Alembic:
```bash
alembic revision --autogenerate -m "initial schema"
```

## CI/CD Integration

### Staging Deploy

```yaml
- name: Generate migrations
  run: |
    cd backend
    ./scripts/migrations_offline.sh

- name: Upload migrations artifact
  uses: actions/upload-artifact@v3
  with:
    name: migrations-sql
    path: backend/artefacts/migrations.sql

- name: Notify DBA
  run: |
    # Send migrations.sql to DBA team for review
```

DBA reviews and applies manually before deployment proceeds.

### Production Deploy

```yaml
- name: Deploy application
  env:
    DATABASE_URL: ${{ secrets.PROD_DATABASE_URL }}
    DB_APPLY_MIGRATIONS: "false"
  run: |
    docker-compose -f docker-compose.prod.yml up -d
```

## Contact

For questions about database migrations or schema changes, contact:
- **DBA Team**: dba@example.com
- **App Team**: dev@example.com


