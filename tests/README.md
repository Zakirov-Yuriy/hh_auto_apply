"""Tests directory for hh_auto_apply."""

# Tests are organized by layer:
#
# tests/
# ├── domain/              Tests for pure business logic (entities, rules)
# ├── infrastructure/      Tests for technical implementations
# │   ├── browser/        Tests for Playwright integration
# │   ├── ai/             Tests for AI/LLM integrations
# │   └── persistence/    Tests for database and storage
# ├── application/        Tests for use cases
# ├── cli/                Tests for CLI and argument parsing
# ├── conftest.py         Shared fixtures (mock_config, etc.)
# └── test_*.py          Specific test files
#
# Run all tests:
#   python -m pytest tests/ -v
#
# Run specific layer:
#   python -m pytest tests/domain/ -v
#   python -m pytest tests/infrastructure/ -v
#
# Run with coverage:
#   python -m pytest tests/ --cov=hh_auto_apply --cov-report=html
