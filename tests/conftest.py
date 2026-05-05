"""Shared pytest fixtures for all tests."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import Mock

from hh_auto_apply.core.config import Config


@pytest.fixture
def mock_config() -> Config:
    """Create a mock Config for testing.

    Returns:
        Mock Config instance with sensible defaults.
    """
    config = Mock(spec=Config)
    config.search_query = "python"
    config.region_ids = []
    config.remote_only = False
    config.max_applies = 200
    config.min_sleep = 1.0
    config.max_sleep = 2.0
    config.persist_dir = ".hh_user"
    config.screenshots_dir = "screenshots"
    config.db_path = ":memory:"  # Use in-memory SQLite for tests
    config.seen_ttl_days = 14
    config.resume_match = "python разработчик"
    config.fail_if_resume_not_found = False
    config.require_cover_letter = False
    config.cover_letter_path = "data/cover_letter.txt"
    config.base_url = "https://hh.ru"
    config.max_pages = 100
    config.empty_pages_tolerance = 3
    config.headless = True
    config.slow_mo_ms = 0
    config.verbose = False
    config.vacancies_csv = "data/vacancies.csv"
    config.failed_vacancies_csv = "data/vacancies_failed.csv"
    config.use_ai_cover_letter = False
    config.openrouter_api_keys = []
    config.ai_prompts_dir = Path("data")
    config.ai_model = "openai/gpt-oss-120b:free"
    return config
