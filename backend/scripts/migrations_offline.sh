#!/bin/bash
# Generate offline SQL migration for DBA handoff

set -e

echo "Generating offline migration SQL..."

# Create artefacts directory
mkdir -p artefacts

# Set schema
export DB_SCHEMA=${DB_SCHEMA:-geo_app}

# Generate SQL
alembic upgrade head --sql > artefacts/migrations.sql

echo "✓ Generated artefacts/migrations.sql"
echo "  Schema: $DB_SCHEMA"
echo ""
echo "Hand this file to your DBA for manual application."
echo "The SQL is idempotent and can be run multiple times safely."


