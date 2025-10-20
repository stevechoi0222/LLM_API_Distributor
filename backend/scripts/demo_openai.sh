#!/usr/bin/env bash
set -euo pipefail

API=${API:-http://localhost:8000}
KEY=${API_KEY:-change_me}
MAPPER_NAME=${MAPPER_NAME:-user_excel_v0_1}
MAPPER_VERSION=${MAPPER_VERSION:-v1}

echo "==> Health check"
curl -s "$API/healthz" | jq . || { echo "API not healthy"; exit 1; }

echo "==> Importing sample data"
IMPORT_RESP=$(curl -s -H "x-api-key: $KEY" -H "Content-Type: application/json" \
  -d @samples/import.json "$API/api/v1/question-sets:import")
echo "$IMPORT_RESP" | jq .

# Extract campaign_id from import response
CAMPAIGN_ID=$(echo "$IMPORT_RESP" | jq -r '.campaign_id // "demo_launch"')
echo "CAMPAIGN_ID=$CAMPAIGN_ID"

echo "==> Creating run (OpenAI)"
RUN_RESP=$(curl -s -H "x-api-key: $KEY" -H "Content-Type: application/json" \
  -d "{
    \"campaign_id\": \"$CAMPAIGN_ID\",
    \"providers\": [{\"name\":\"openai\",\"model\":\"gpt-4o-mini\",\"temperature\":0}],
    \"prompt_version\": \"v1\",
    \"concurrency\": 3,
    \"rate_limits\": {\"openai\":{\"qps\":2,\"burst\":4}}
  }" "$API/api/v1/runs")
echo "$RUN_RESP" | jq .

RUN_ID=$(echo "$RUN_RESP" | jq -r '.id')
echo "RUN_ID=$RUN_ID"

echo "==> Starting run"
curl -s -H "x-api-key: $KEY" -X POST "$API/api/v1/runs/$RUN_ID/start" | jq .

echo "==> Polling run status"
for i in {1..60}; do
  RUN_STATUS=$(curl -s -H "x-api-key: $KEY" "$API/api/v1/runs/$RUN_ID")
  STATUS=$(echo "$RUN_STATUS" | jq -r '.status')
  PENDING=$(echo "$RUN_STATUS" | jq -r '.counts.pending')
  RUNNING=$(echo "$RUN_STATUS" | jq -r '.counts.running')
  SUCCEEDED=$(echo "$RUN_STATUS" | jq -r '.counts.succeeded')
  FAILED=$(echo "$RUN_STATUS" | jq -r '.counts.failed')
  
  echo "[Poll $i/60] status=$STATUS pending=$PENDING running=$RUNNING succeeded=$SUCCEEDED failed=$FAILED"
  
  [[ "$PENDING" == "0" && "$RUNNING" == "0" ]] && break
  sleep 2
done

echo "==> Final run status"
curl -s -H "x-api-key: $KEY" "$API/api/v1/runs/$RUN_ID" | jq .

echo "==> Exporting to XLSX ($MAPPER_NAME / $MAPPER_VERSION)"
EXPORT_RESP=$(curl -s -H "x-api-key: $KEY" -H "Content-Type: application/json" \
  -d "{
    \"run_id\": \"$RUN_ID\",
    \"format\": \"xlsx\",
    \"mapper_name\":\"$MAPPER_NAME\",
    \"mapper_version\":\"$MAPPER_VERSION\"
  }" "$API/api/v1/exports")
echo "$EXPORT_RESP" | jq .

EXPORT_ID=$(echo "$EXPORT_RESP" | jq -r '.id')
echo "EXPORT_ID=$EXPORT_ID"

# Poll export status
echo "==> Polling export status"
for i in {1..30}; do
  EXPORT_STATUS=$(curl -s -H "x-api-key: $KEY" "$API/api/v1/exports/$EXPORT_ID")
  STATUS=$(echo "$EXPORT_STATUS" | jq -r '.status')
  FILE_URL=$(echo "$EXPORT_STATUS" | jq -r '.file_url // empty')
  
  echo "[Poll $i/30] export_status=$STATUS file_url=$FILE_URL"
  
  if [[ "$STATUS" == "completed" && -n "$FILE_URL" ]]; then
    echo ""
    echo "=========================================="
    echo "✓ DEMO COMPLETED SUCCESSFULLY"
    echo "=========================================="
    echo "XLSX created at: $FILE_URL"
    echo "Run ID: $RUN_ID"
    echo "Export ID: $EXPORT_ID"
    echo "=========================================="
    exit 0
  fi
  
  if [[ "$STATUS" == "failed" ]]; then
    echo "Export failed!"
    exit 1
  fi
  
  sleep 1
done

echo "Warning: Export did not complete in time; check server logs."

