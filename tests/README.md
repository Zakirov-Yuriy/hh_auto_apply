"""Директория тестов для hh_auto_apply."""

# Тесты организованы по слоям:
#
# tests/
# ├── domain/              Тесты для чистой бизнес-логики (entities, rules)
# ├── infrastructure/      Тесты для технических реализаций
# │   ├── browser/        Тесты для интеграции с Playwright
# │   ├── ai/             Тесты для AI/LLM интеграций
# │   └── persistence/    Тесты для базы данных и хранилища
# ├── application/        Тесты для use cases
# ├── cli/                Тесты для CLI и парсинга аргументов
# ├── conftest.py         Общие fixtures (mock_config, и т.д.)
# └── test_*.py          Конкретные тестовые файлы
#
# Запустить все тесты:
#   python -m pytest tests/ -v
#
# Запустить конкретный слой:
#   python -m pytest tests/domain/ -v
#   python -m pytest tests/infrastructure/ -v
#
# Запустить с покрытием:
#   python -m pytest tests/ --cov=hh_auto_apply --cov-report=html

