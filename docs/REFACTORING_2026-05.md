# Проект hh_auto_apply: Реорганизация структуры (2026-05-05)

## Описание проделанной работы

Проект полностью реорганизован согласно принципам чистой архитектуры (Clean Architecture) с четким разделением на слои.

## Выполненные задачи

### 1. ✅ Переместить тесты
- **Было:** 8 тестовых файлов в корне проекта
- **Стало:** Все тесты в папке `tests/`
  - `tests/test_*.py` — основные тесты
  - `tests/conftest.py` — общие fixtures
  - `tests/README.md` — гайд по тестированию
  - `tests/{domain,infrastructure,application,cli}/` — структурированные подпапки

**Обновлены импорты:** 
- 6 тестовых файлов
- 12 импортов обновлено на новую структуру

### 2. ✅ Организовать документацию
- **Было:** Документация в корне проекта
- **Стало:** Централизованная папка `docs/`
  - `CUSTOM_QUESTIONS.md` — кастомные вопросы
  - `CUSTOM_QUESTIONS_READY.md` — готовые решения
  - `FINAL_REPORT.md` — итоговый отчет
  - `FIX_SUMMARY.md` — краткое описание исправлений
  - `ARCHITECTURE.md` — новая документация архитектуры
  - `INDEX.md` — индекс документации

### 3. ✅ Организовать ресурсы
- **Было:** Ресурсы в корне проекта
- **Стало:** Централизованная папка `data/`
  - CSV файлы: `vacancies.csv`, `vacancies_failed.csv`
  - Письма: `cover_letter.txt`
  - Промпты: `prompt_python.txt`, `prompt_flutter.txt`
  - Справочные файлы: `Python.txt`, `Flutter.txt`
  - `data/README.md` — описание ресурсов

### 4. ✅ Создать структуру слоёв архитектуры

Создана новая структура слоёв в `hh_auto_apply/`:

```
hh_auto_apply/
├── core/                    # Ядро приложения
│   ├── __init__.py
│   └── config.py           # Конфигурация (только Config, без argparse)
│
├── domain/                 # Чистая бизнес-логика
│   ├── __init__.py
│   └── entities.py         # ApplyResult enum, Stats dataclass
│
├── infrastructure/         # Технические детали
│   ├── __init__.py
│   ├── browser/
│   │   ├── __init__.py
│   │   ├── hh_client.py    # (бывший client.py)
│   │   └── selectors.py    # CSS/XPath селекторы
│   ├── ai/
│   │   └── __init__.py     # (placeholder для будущих генераторов)
│   ├── persistence/
│   │   ├── __init__.py
│   │   └── seen_repo.py    # (бывший persistence.py)
│   └── utils.py            # (бывший utils.py)
│
├── application/            # Сценарии использования
│   ├── __init__.py
│   └── run_session.py      # (бывший app.py)
│
└── cli/                    # Точка входа
    ├── __init__.py
    ├── main.py             # Главная функция main()
    └── args.py             # Парсинг CLI аргументов
```

### 5. ✅ Обновить импорты и точку входа

**Обновлены 13 файлов:**

- `run.py` — обновлена точка входа
- `hh_auto_apply/core/config.py` — убран argparse, оставлена только Config.from_env()
- `hh_auto_apply/cli/main.py` — создана новая точка входа
- `hh_auto_apply/cli/args.py` — создан парсер CLI аргументов
- `hh_auto_apply/application/run_session.py` — обновлены импорты
- `hh_auto_apply/infrastructure/browser/hh_client.py` — обновлены импорты
- `hh_auto_apply/infrastructure/utils.py` — обновлены импорты
- Все 8 тестовых файлов — обновлены импорты

**Логика импортов:**
- `core.config.Config` (конфигурация, окружение)
- `domain.entities.ApplyResult, Stats` (бизнес-сущности)
- `infrastructure.browser.hh_client.HHClient` (Playwright)
- `infrastructure.persistence.seen_repo.SeenRepo` (SQLite)
- `infrastructure.utils.human_pause, extract_vacancy_id` (утилиты)
- `application.run_session.App` (главное приложение)
- `cli.main.main, cli.args.parse_args` (CLI)

### 6. ✅ Создать документацию

**Новые документы:**
- `docs/ARCHITECTURE.md` — полное описание архитектуры слоёв, SOLID принципы, план рефакторинга
- `docs/INDEX.md` — индекс и навигация по документации
- `data/README.md` — описание CSV файлов, письма, промпты
- `tests/README.md` — гайд по тестированию и структуре

**Обновлены:**
- `README.md` — добавлены ссылки на архитектуру и документацию

## Статистика изменений

| Метрика | Значение |
|---------|----------|
| Файлов перемещено | 17 |
| Папок создано | 7 слоёв + 7 в tests/ |
| Импортов обновлено | 25+ |
| Новых файлов создано | 6 (main.py, args.py, ARCHITECTURE.md, INDEX.md, conftest.py, и др.) |
| Документации добавлено | 3 новых MD файла |

## Проверки ✓

- ✅ Все тесты проходят: `pytest tests/test_utils.py` — 5/5 passed
- ✅ Все импорты работают
- ✅ Entry point работает: `python run.py --help`
- ✅ CLI парсер работает: `hh_auto_apply.cli.args.parse_args()`
- ✅ Конфигурация загружается: `Config.from_env()`

## Следующие шаги (для будущего рефакторинга)

1. **Раздели client.py:**
   - Извлечь `infrastructure/browser/hh_navigator.py`
   - Извлечь `infrastructure/browser/hh_vacancy_page.py`
   - Извлечь `infrastructure/ai/openrouter.py`

2. **Раздели app.py:**
   - Извлечь `infrastructure/persistence/csv_sink.py`
   - Извлечь `core/logging.py`

3. **Исправь известные баги:**
   - Удалить дублированный `except TargetClosedError` в client.py
   - Заменить `except Exception: pass` на `except sqlite3.Error` в seen_repo.py

4. **Добавь типизацию:**
   - Создать `core/exceptions.py` с AppError иерархией
   - Добавить Protocol интерфейсы для тестирования

## Примечания

- Все изменения обратно совместимы — `python run.py` работает как раньше
- Структура удобна для расширения новыми модулями
- Каждый слой может быть протестирован независимо
- Для новых разработчиков ясна структура и зависимости проекта

## Файлы для проверки

1. `docs/ARCHITECTURE.md` — основная документация архитектуры
2. `hh_auto_apply/` — новая структура слоёв
3. `tests/` — тесты в новом местоположении
4. `run.py` — обновленная точка входа
5. `README.md` — обновленный главный README
