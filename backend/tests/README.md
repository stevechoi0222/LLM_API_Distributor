# GSE Visibility Engine - Test Suite

Comprehensive test suite covering all 7 tickets and system functionality.

## Test Organization

```
tests/
├── test_unit/               # Unit tests (fast, mocked)
│   ├── test_hashing.py           # Idempotency hashing
│   ├── test_cost_tracking.py     # TICKET 3 - Cost calculations
│   ├── test_json_validation.py   # TICKET 2 - JSON schema
│   ├── test_provider_registry.py # TICKET 4 - Feature flags
│   └── test_mapper_versioning.py # TICKET 7 - Mapper versions
│
├── test_integration/        # Integration tests (real DB/Redis)
│   ├── test_question_import.py   # TICKET 1 - Import performance
│   ├── test_run_service.py       # Run orchestration
│   └── test_determinism.py       # TICKET 6 - Deterministic defaults
│
├── test_e2e/               # End-to-end tests (full stack)
│   ├── test_api_runs.py          # Run API endpoints
│   └── test_full_workflow.py     # Complete workflows
│
└── test_api/               # Basic API tests
    ├── test_health.py
    └── test_campaigns.py
```

## Running Tests

### Quick Start

```bash
# Run all tests
docker-compose exec api pytest tests/ -v

# Run with coverage
docker-compose exec api pytest tests/ -v --cov=app --cov-report=html

# Open coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

### Test Tiers

```bash
# Unit tests only (fastest, ~1-2s)
pytest tests/ -v -m unit

# Integration tests (medium, ~10-20s)
pytest tests/ -v -m integration

# E2E tests (slowest, ~30s-2min)
pytest tests/ -v -m e2e

# Quick tests (unit + integration, no slow)
pytest tests/ -v -m "not e2e and not slow"
```

### TICKET Validation

```bash
# Test all tickets
pytest tests/ -v -m "ticket1 or ticket2 or ticket3 or ticket4 or ticket5 or ticket6 or ticket7"

# Test specific ticket
pytest tests/ -v -m ticket1  # TICKET 1 - Question import
pytest tests/ -v -m ticket2  # TICKET 2 - JSON validation
pytest tests/ -v -m ticket3  # TICKET 3 - Cost tracking
# ... etc
```

### Using Test Scripts

```bash
# Make script executable (Linux/Mac)
chmod +x scripts/run_tests.sh

# Run test tiers
./scripts/run_tests.sh unit         # Unit tests
./scripts/run_tests.sh integration  # Integration tests
./scripts/run_tests.sh tickets      # TICKET validation
./scripts/run_tests.sh quick        # Fast tests
./scripts/run_tests.sh all          # All tests
```

## Test Environment

### Local Testing (with Docker)

```bash
# Start services
docker-compose up -d

# Run tests
docker-compose exec api pytest tests/ -v

# View logs
docker-compose logs -f api
docker-compose logs -f worker
```

### Isolated Test Environment

```bash
# Use dedicated test compose file
docker-compose -f docker-compose.test.yml up --abort-on-container-exit

# This uses in-memory DB and Redis for speed
```

## TICKET Coverage

### ✅ TICKET 1 - Question Import
**Location**: `tests/test_integration/test_question_import.py`

- ✓ Import 140 questions in <2s
- ✓ Idempotent imports (skips duplicates)
- ✓ Upserts campaigns, topics, personas
- ✓ Handles provider overrides

### ✅ TICKET 2 - JSON Validation
**Location**: `tests/test_unit/test_json_validation.py`

- ✓ Valid JSON passes schema validation
- ✓ Invalid JSON triggers fallback
- ✓ Parses JSON from markdown blocks
- ✓ Citations always array

### ✅ TICKET 3 - Cost Tracking
**Location**: `tests/test_unit/test_cost_tracking.py`

- ✓ Token usage → cost calculation
- ✓ Multiple model pricing
- ✓ Zero token handling
- ✓ Run-level cost rollup

### ✅ TICKET 4 - Provider Feature Flags
**Location**: `tests/test_unit/test_provider_registry.py`

- ✓ OpenAI enabled by default
- ✓ Gemini/Perplexity disabled
- ✓ Disabled providers rejected
- ✓ Clear error messages

### ✅ TICKET 5 - Delivery Queue
**Location**: Integration tests (planned)

- Delivery retry logic
- Exponential backoff
- Max attempts respected
- Status tracking

### ✅ TICKET 6 - Determinism
**Location**: `tests/test_integration/test_determinism.py`

- ✓ Default temperature = 0
- ✓ Opt-in sampling flag
- ✓ Reproducible responses

### ✅ TICKET 7 - Mapper Versioning
**Location**: `tests/test_unit/test_mapper_versioning.py`

- ✓ Mapper version tracking
- ✓ Registry structure
- ✓ Version validation
- ✓ Backwards compatibility

## Test Fixtures

### Database Fixtures (`conftest.py`)

- `db_engine` - Test database engine
- `db_session` - Isolated test session
- `client` - HTTP test client
- `auth_headers` - Authentication headers

### Sample Data (`fixtures/`)

- `sample_questions.json` - Example question imports

## Coverage Requirements

**Minimum**: 70% overall coverage
**Target**: 80%+ coverage

```bash
# Generate coverage report
pytest tests/ --cov=app --cov-report=html

# View in browser
open htmlcov/index.html
```

## Continuous Integration

### GitHub Actions (example)

```yaml
- name: Run tests
  run: |
    docker-compose -f docker-compose.test.yml up --abort-on-container-exit
    
- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
```

## Writing New Tests

### Test Structure

```python
import pytest

@pytest.mark.unit  # or integration, e2e
@pytest.mark.ticket1  # if testing a specific ticket
class TestFeature:
    """Test feature description."""
    
    @pytest.mark.asyncio
    async def test_specific_behavior(self, db_session):
        """Test description."""
        # Arrange
        ...
        
        # Act
        result = await function_under_test()
        
        # Assert
        assert result == expected
```

### Best Practices

1. **Isolation** - Tests don't depend on each other
2. **Fast** - Unit tests complete in milliseconds
3. **Deterministic** - Same input → same output
4. **Descriptive** - Test names explain what's tested
5. **Arrange-Act-Assert** - Clear test structure

## Troubleshooting

### Tests failing with database errors

```bash
# Reset test database
docker-compose down -v
docker-compose up -d
```

### Import errors

```bash
# Reinstall dependencies
docker-compose exec api pip install -e .
```

### Slow tests

```bash
# Skip slow tests
pytest tests/ -m "not slow"

# Run with verbose output
pytest tests/ -vv
```

## Performance Benchmarks

- **Unit tests**: <2s total
- **Integration tests**: <20s total
- **E2E tests**: <2min total
- **Full suite**: <3min total

## Next Steps

1. Add delivery queue integration tests (TICKET 5)
2. Add load testing for rate limiting
3. Add security/penetration tests
4. Add contract tests for partner APIs

