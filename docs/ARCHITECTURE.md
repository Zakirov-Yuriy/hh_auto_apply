# Архитектура проекта hh_auto_apply

Проект организован согласно принципам **чистой архитектуры (Clean Architecture)** с четкой разделением на слои.

## Структура слоёв

```
hh_auto_apply/
├── core/                    # Ядро приложения (конфигурация, исключения, логирование)
│   ├── config.py           # Конфигурация (Config dataclass)
│   ├── exceptions.py       # Типизированные исключения (AppError и его подклассы)
│   └── logging.py          # Настройка логирования (будет добавлено)
│
├── domain/                 # Бизнес-логика (чистые сущности и правила)
│   └── entities.py         # ApplyResult enum, Stats dataclass
│
├── infrastructure/         # Реализация технических деталей
│   ├── browser/           # Взаимодействие с Playwright
│   │   ├── hh_client.py   # Основной клиент для hh.ru (будет разбит)
│   │   └── selectors.py   # CSS/XPath селекторы
│   ├── ai/                # Генерация сопроводительных писем
│   │   ├── generator.py   # Интерфейс ICoverLetterGenerator
│   │   ├── openrouter.py  # Реализация через OpenRouter
│   │   ├── static.py      # Реализация со статическим файлом
│   │   └── prompt_loader.py  # Загрузка и форматирование промптов
│   ├── persistence/       # Сохранение данных
│   │   ├── seen_repo.py   # ISeenRepo и SqliteSeenRepo
│   │   └── csv_sink.py    # CsvVacancySink (будет добавлено)
│   └── utils.py           # Утилиты (human_pause, extract_vacancy_id)
│
├── application/           # Прикладные сценарии использования (use cases)
│   ├── run_session.py     # App класс - главная сессия (будет разбит)
│   └── apply_one_vacancy.py  # Сценарий применения к одной вакансии (будет добавлено)
│
└── cli/                   # Точка входа и CLI
    ├── main.py           # Главная функция main()
    └── args.py           # Парсинг аргументов командной строки
```

## Правила архитектуры

### 1. **Domain Layer** (Слой сущностей)
- Содержит только чистый Python, без зависимостей от I/O
- **Нет импортов из:** `infrastructure`, `application`, `cli`
- **Содержит:** сущности (Vacancy, Resume, Stats), правила (ResumeMatcher), enum'ы (ApplyResult)

### 2. **Infrastructure Layer** (Слой технических деталей)
- Реализует интерфейсы, определенные в domain или рядом с собой
- **Структура:**
  - `browser/` — Playwright, селекторы, навигация
  - `ai/` — HTTP запросы к AI провайдерам, кэширование
  - `persistence/` — SQLite, CSV, база данных
- **Правило:** модули в одной подпапке НЕ импортируют из других (`browser` не импортирует из `ai`)

### 3. **Application Layer** (Слой сценариев использования)
- Координирует компоненты infrastructure для выполнения бизнес-сценариев
- **Зависит от:** domain interfaces + infrastructure implementations
- **Передает:** результаты в CLI для вывода пользователю

### 4. **CLI Layer** (Точка входа)
- Единственное место, которое составляет зависимости (Dependency Injection)
- Парсит аргументы командной строки
- Создает конкретные реализации (Config, HHClient, SeenRepo, etc.)
- Трансформирует исключения в коды выхода

## Зависимости между слоями

```
CLI
 ↓
Application
 ↓
Infrastructure  ←→  Domain
```

**Важно:** Domain никогда не зависит от других слоёв.

## Файловые ресурсы

```
data/
├── vacancies.csv              # Успешно обработанные вакансии
├── vacancies_failed.csv       # Вакансии с ошибками
├── cover_letter.txt           # Стандартное сопроводительное письмо
├── prompt_python.txt          # Промпт для Python вакансий (AI)
├── prompt_flutter.txt         # Промпт для Flutter вакансий (AI)
├── Python.txt                 # Примеры Python вопросов
└── Flutter.txt                # Примеры Flutter вопросов

docs/
├── ARCHITECTURE.md            # Этот файл
├── CUSTOM_QUESTIONS.md        # Документация по кастомным вопросам
├── CUSTOM_QUESTIONS_READY.md  # Готовые решения
├── FINAL_REPORT.md            # Итоговый отчет
└── FIX_SUMMARY.md             # Краткое описание исправлений
```

## Примеры импортов

### ✓ Правильно
```python
# В cli/main.py
from hh_auto_apply.core.config import Config
from hh_auto_apply.application.run_session import App
from hh_auto_apply.infrastructure.browser.hh_client import HHClient

# В application/run_session.py
from hh_auto_apply.domain.entities import ApplyResult
from hh_auto_apply.infrastructure.persistence.seen_repo import SeenRepo

# В infrastructure/browser/hh_client.py
from hh_auto_apply.domain.entities import ApplyResult
from hh_auto_apply.infrastructure.utils import human_pause
```

### ✗ Неправильно
```python
# В domain/entities.py
from hh_auto_apply.infrastructure.browser.hh_client import HHClient  # ✗ Domain зависит от Infrastructure

# В infrastructure/browser/hh_client.py
from hh_auto_apply.infrastructure.ai.openrouter import OpenRouter  # ✗ Кросс-модульная зависимость

# В infrastructure/browser/hh_client.py
import sys; sys.exit(1)  # ✗ sys.exit только в cli/main.py
```

## Entry Point

```
run.py (корень)
  ↓
hh_auto_apply/cli/main.py:main()
  ↓
hh_auto_apply/cli/args.py:parse_args()
  ↓
hh_auto_apply/core/config.py:Config.from_env()
  ↓
hh_auto_apply/application/run_session.py:App.run()
```

## Запуск

```bash
# Через run.py
python run.py --headless --query "Python"

# Через модуль
python -m hh_auto_apply.cli.main --dry-run

# Через pytest
python -m pytest tests/ -v
```

## Рефакторинг: План миграции

### Phase 1: Завершить (текущие работы)
- ✓ Переместить тесты в `tests/`
- ✓ Организовать документацию в `docs/`
- ✓ Организовать ресурсы в `data/`
- ✓ Создать слои архитектуры

### Phase 2: Раздели client.py
- [ ] Извлечь `infrastructure/browser/hh_navigator.py` (build_search_url, ensure_logged_in, list_vacancy_links)
- [ ] Извлечь `infrastructure/browser/hh_vacancy_page.py` (apply_to_vacancy, select_resume, fill_letter)
- [ ] Извлечь `infrastructure/ai/openrouter.py` (HTTP вызовы, retry, кэширование)
- [ ] Удалить `infrastructure/browser/hh_client.py`

### Phase 3: Раздели app.py
- [ ] Извлечь `infrastructure/persistence/csv_sink.py`
- [ ] Извлечь `core/logging.py`
- [ ] Извлечь `application/apply_one_vacancy.py`
- [ ] Оставить `application/run_session.py` как главный loop

### Phase 4: Исправь ошибки (из copilot-instructions.md)
- [ ] Удалить дублированный `except TargetClosedError` в client.py
- [ ] Заменить `except Exception: pass` на `except sqlite3.Error`
- [ ] Добавить `@tenacity.retry` вокруг OpenRouter вызовов
- [ ] Создать `core/exceptions.py` с AppError иерархией

## SOLID принципы

- **S**ingleton Responsibility: Каждый класс одна ответственность (Playwright, HTTP, SQLite, Business logic)
- **O**pen/Closed: Легко добавить новый cover-letter генератор через интерфейс
- **L**iskov: Subclasses honorят контракт (все генераторы возвращают str или Exception)
- **I**nterface Segregation: Маленькие интерфейсы (ISeenRepo, ICoverLetterGenerator)
- **D**ependency Inversion: App зависит от интерфейсов, не от конкретных реализаций
