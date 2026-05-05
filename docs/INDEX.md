# Документация проекта hh_auto_apply

## Основные документы

### [ARCHITECTURE.md](ARCHITECTURE.md)
Описание структуры проекта согласно принципам чистой архитектуры. 
- Структура слоёв (core, domain, infrastructure, application, cli)
- Правила зависимостей между слоями
- Примеры правильных и неправильных импортов
- План рефакторинга

### [CUSTOM_QUESTIONS.md](CUSTOM_QUESTIONS.md)
Документация по обработке кастомных вопросов при подаче откликов.
- Типы вопросов
- Как их обнаружить
- Как генерировать ответы

### [CUSTOM_QUESTIONS_READY.md](CUSTOM_QUESTIONS_READY.md)
Готовые решения и примеры ответов на кастомные вопросы.

### [FINAL_REPORT.md](FINAL_REPORT.md)
Итоговый отчет о последних изменениях и улучшениях.

### [FIX_SUMMARY.md](FIX_SUMMARY.md)
Краткое описание исправленных багов и улучшений.

## Быстрые ссылки

### Для разработчиков
- Начните с [ARCHITECTURE.md](ARCHITECTURE.md) для понимания структуры
- Смотрите `hh_auto_apply/` для исходного кода
- Смотрите `tests/` для примеров использования

### Для пользователей
- [README.md](../README.md) в корне проекта
- `data/` для ресурсов (письма, промпты)

### Для тестирования
- `tests/` — все тесты
- Запуск: `python -m pytest tests/ -v`

## Структура проекта

```
hh_auto_apply/
├── core/               # Конфигурация и исключения
├── domain/             # Бизнес-логика
├── infrastructure/     # Технические детали (Playwright, HTTP, SQLite)
├── application/        # Сценарии использования
└── cli/                # CLI и точка входа

data/
├── *.csv              # Результаты применения
├── *.txt              # Письма и промпты

docs/                 # Документация (этот folder)

tests/                # Тесты
```

## Ключевые компоненты

| Компонент | Расположение | Назначение |
|-----------|------------|-----------|
| Config | `core/config.py` | Загрузка конфигурации из окружения |
| ApplyResult | `domain/entities.py` | Enum результатов применения |
| Stats | `domain/entities.py` | Статистика сессии |
| HHClient | `infrastructure/browser/hh_client.py` | Основной клиент для работы с hh.ru |
| Selectors | `infrastructure/browser/selectors.py` | CSS/XPath селекторы |
| SeenRepo | `infrastructure/persistence/seen_repo.py` | Хранилище посещённых вакансий (SQLite) |
| App | `application/run_session.py` | Главный класс приложения |
| main | `cli/main.py` | Точка входа приложения |

## Entry Point

```
python run.py [--headless] [--dry-run] [--verbose] [--query "QUERY"]
```

## Развертывание

1. Установите зависимости: `pip install -r requirements.txt`
2. Создайте `.env` файл с переменными окружения
3. Запустите: `python run.py`
