# Demo Scripts

This directory contains automated demo scripts for testing the LLM API Distributor end-to-end.

## Prerequisites

- Docker & Docker Compose installed
- `jq` installed (`brew install jq` on macOS, `apt-get install jq` on Ubuntu)
- `.env` file configured in `backend/` directory
- Services running (`make up` from project root)

## Scripts

### `demo_openai.sh`

Runs a complete demo using OpenAI only.

**Requirements**:
- `ENABLE_OPENAI=true` in `.env`
- `OPENAI_API_KEY` set in `.env`

**Usage**:
```bash
# From project root
make demo-openai

# Or directly
cd backend
bash scripts/demo_openai.sh
```

**What it does**:
1. Health check (`/healthz`)
2. Import 2 sample questions from `samples/import.json`
3. Create run with OpenAI (gpt-4o-mini, temperature=0)
4. Start run and poll until completion
5. Export to XLSX using `user_excel_v0_1` mapper
6. Print output file path

**Expected output**:
```
========================================
✓ DEMO COMPLETED SUCCESSFULLY
========================================
XLSX created at: artefacts/user_excel_v0_1_<run_id>.xlsx
Run ID: <run_id>
Export ID: <export_id>
========================================
```

### `demo_multi.sh`

Runs a demo with multiple providers (OpenAI, Gemini, Perplexity).

**Requirements**:
- `ENABLE_OPENAI=true`, `ENABLE_GEMINI=true`, `ENABLE_PERPLEXITY=true` in `.env`
- `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `PERPLEXITY_API_KEY` set in `.env`

**Usage**:
```bash
# From project root
make demo-multi

# Or directly
cd backend
bash scripts/demo_multi.sh
```

**What it does**:
Same as `demo_openai.sh`, but creates a run with 3 providers. The output XLSX will contain separate rows for each provider in the AI_API_04_QUERY sheet.

**Expected output**:
```
========================================
✓ MULTI-PROVIDER DEMO COMPLETED
========================================
XLSX created at: artefacts/user_excel_v0_1_<run_id>.xlsx
Run ID: <run_id>
Export ID: <export_id>

The XLSX contains results from:
  - OpenAI (gpt-4o-mini)
  - Gemini (gemini-1.5-flash)
  - Perplexity (llama-3.1-sonar-small)
========================================
```

## Environment Variables

Both scripts support customization via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `API` | `http://localhost:8000` | API base URL |
| `API_KEY` | `change_me` | API key for authentication |
| `MAPPER_NAME` | `user_excel_v0_1` | Export mapper name |
| `MAPPER_VERSION` | `v1` | Export mapper version |

**Example with custom API URL**:
```bash
API=http://192.168.1.100:8000 API_KEY=my-key bash scripts/demo_openai.sh
```

## Troubleshooting

### Script fails with "API not healthy"

**Cause**: Services not fully initialized

**Solution**: Wait 10-15 seconds after `make up` before running demo

### Import fails with 404

**Cause**: `samples/import.json` file missing or wrong working directory

**Solution**: Ensure you're running from `backend/` directory and file exists

### Run stuck in "pending" status

**Cause**: Celery workers not processing tasks

**Solution**: 
1. Check worker logs: `docker compose logs celery`
2. Verify Redis is running: `docker compose ps redis`
3. Check API key is valid

### Export status never becomes "completed"

**Cause**: Export task failed or not queued

**Solution**:
1. Check API logs: `docker compose logs api`
2. Check Celery logs: `docker compose logs celery`
3. Verify `artefacts/` directory exists and is writable

### "jq: command not found"

**Cause**: `jq` not installed

**Solution**:
- macOS: `brew install jq`
- Ubuntu/Debian: `apt-get install jq`
- Windows: Use WSL or download from https://stedolan.github.io/jq/

## Output Files

Both scripts generate XLSX files in `backend/artefacts/`:

**Filename format**: `user_excel_v0_1_{run_id}.xlsx`

**Contents**:
- **Sheet 1: AI_API_04_QUERY**
  - Columns: campaign, run_id, question_id, persona_name, question_text, provider, model, response_text, latency_ms, prompt_tokens, completion_tokens, cost_cents, status
  - One row per (provider × question) combination
  
- **Sheet 2: AI_API_08_CITATION**
  - Columns: run_id, question_id, provider, citation_index, citation_url
  - One row per citation URL (0-based indexing)

## Customizing the Demo

### Change the questions

Edit `samples/import.json` to change the demo questions:

```json
[
  {
    "campaign": "your_campaign",
    "topic": {"title": "Your Topic"},
    "persona": {"name":"YourName","role":"Your Role","locale":"en-US","tone":"neutral"},
    "question": {"id":"Q_001","text":"Your question here?"}
  }
]
```

### Change provider settings

Edit the `providers` array in the script:

```bash
# In demo_openai.sh or demo_multi.sh
"providers": [
  {"name":"openai","model":"gpt-4o","temperature":0.7},  # Different model & temp
  {"name":"gemini","model":"gemini-pro","temperature":0}
]
```

### Change rate limits

Edit the `rate_limits` object:

```bash
"rate_limits": {
  "openai":{"qps":5,"burst":10},  # Higher rates
  "gemini":{"qps":3,"burst":6}
}
```

## Integration with CI/CD

These scripts can be used in CI/CD pipelines for integration testing:

```yaml
# Example GitHub Actions workflow
- name: Run Demo Test
  run: |
    make up
    sleep 15  # Wait for services
    make demo-openai
    test -f backend/artefacts/user_excel_v0_1_*.xlsx
```

## Support

For issues or questions:
1. Check logs: `docker compose logs`
2. Verify `.env` configuration
3. Review DELIVERY_RUNBOOK.md
4. Check API health: `curl http://localhost:8000/healthz`

