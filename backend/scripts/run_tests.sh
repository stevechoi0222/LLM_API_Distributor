#!/bin/bash
# Test runner script

set -e

echo "🧪 Running GSE Visibility Engine Tests"
echo "======================================="
echo ""

# Parse arguments
TEST_TIER="${1:-all}"

case $TEST_TIER in
  unit)
    echo "Running Unit Tests (fast)..."
    pytest tests/ -v -m unit --cov=app --cov-report=term-missing
    ;;
  
  integration)
    echo "Running Integration Tests..."
    pytest tests/ -v -m integration --cov=app --cov-report=term-missing
    ;;
  
  e2e)
    echo "Running E2E Tests..."
    pytest tests/ -v -m e2e --cov=app --cov-report=term-missing
    ;;
  
  tickets)
    echo "Running TICKET Validation Tests..."
    pytest tests/ -v -m "ticket1 or ticket2 or ticket3 or ticket4 or ticket5 or ticket6 or ticket7" --cov=app --cov-report=html
    echo ""
    echo "✅ Coverage report generated in htmlcov/index.html"
    ;;
  
  quick)
    echo "Running Quick Tests (unit + integration, no slow tests)..."
    pytest tests/ -v -m "not e2e and not slow" --cov=app --cov-report=term-missing
    ;;
  
  all)
    echo "Running All Tests..."
    pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing
    echo ""
    echo "✅ Coverage report generated in htmlcov/index.html"
    ;;
  
  *)
    echo "Usage: $0 [unit|integration|e2e|tickets|quick|all]"
    echo ""
    echo "Options:"
    echo "  unit        - Run unit tests only (fast)"
    echo "  integration - Run integration tests (DB/Redis required)"
    echo "  e2e         - Run end-to-end tests (full stack)"
    echo "  tickets     - Run TICKET validation tests"
    echo "  quick       - Run unit + integration (no slow tests)"
    echo "  all         - Run all tests (default)"
    exit 1
    ;;
esac

echo ""
echo "✅ Tests completed!"

