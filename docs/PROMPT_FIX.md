# Исправление: Загрузка промптов из папки data/

## Проблема
После переноса файлов в папку `data/`, система не могла найти файлы промптов:
```
Файл с промптом не найден: prompt_python.txt  он находиться data\prompt_python.txt
```

## Решение

### Изменения в архитектуре

#### 1. **core/config.py** — обновлена конфигурация
- **Было:** `ai_prompt_path: Path | None = None` (конкретный файл промпта)
- **Стало:** `ai_prompts_dir: Path = Path("data")` (директория с промптами)

**Причина:** Система должна динамически выбирать промпт (python, flutter) в зависимости от поискового запроса.

#### 2. **infrastructure/browser/hh_client.py** — добавлена логика определения промпта

**Новый метод `_get_prompt_file()`:**
```python
def _get_prompt_file(self) -> Path:
    """Определяет и возвращает путь к файлу промпта на основе search_query."""
    search_query = self.cfg.search_query.lower()
    
    # 1. Ищет специфичный для типа поиска файл
    if "flutter" in search_query:
        prompt_file = self.cfg.ai_prompts_dir / "prompt_flutter.txt"
        if prompt_file.exists():
            return prompt_file
    
    if "python" in search_query:
        prompt_file = self.cfg.ai_prompts_dir / "prompt_python.txt"
        if prompt_file.exists():
            return prompt_file
    
    # 2. Fallback: ищет generic файл
    generic_prompt = self.cfg.ai_prompts_dir / "prompt.txt"
    if generic_prompt.exists():
        return generic_prompt
    
    # 3. Если ничего не найдено - выбрасывает детальную ошибку
    raise FileNotFoundError(f"Файл с промптом не найден в {self.cfg.ai_prompts_dir}/")
```

**Обновлен метод `_generate_cover_letter()`:**
```python
try:
    prompt_file = self._get_prompt_file()  # Динамически определяем файл
    prompt_template = prompt_file.read_text(encoding="utf-8")
    logger.info(f"Генерация сопроводительного письма с помощью ИИ (файл: {prompt_file.name})")
except FileNotFoundError as e:
    logger.error(str(e))
    return ""
```

## Логика поиска промпта

```
search_query = "python разработчик"
            ↓
    1. Проверить: data/prompt_python.txt ✓ НАЙДЕН
            ↓
    Использовать: data/prompt_python.txt

---

search_query = "flutter developer"
            ↓
    1. Проверить: data/prompt_flutter.txt ✓ НАЙДЕН
            ↓
    Использовать: data/prompt_flutter.txt

---

search_query = "golang expert"
            ↓
    1. Проверить: data/prompt_golang.txt ✗ не найден
    2. Проверить: data/prompt.txt ✓ НАЙДЕН (fallback)
            ↓
    Использовать: data/prompt.txt
```

## Файлы промптов в data/

```
data/
├── prompt_python.txt    - Специфичный промпт для Python поиска
├── prompt_flutter.txt   - Специфичный промпт для Flutter поиска
└── prompt.txt          - Generic промпт (fallback)
```

## Переменная окружения

Можно переопределить директорию промптов через `.env`:
```dotenv
AI_PROMPTS_DIR="data"     # По умолчанию
AI_PROMPTS_DIR="./prompts"  # Кастомная папка
```

## Сообщения логирования

```
DEBUG: "Найден Python промпт: data\prompt_python.txt"
INFO:  "Генерация сопроводительного письма с помощью ИИ (файл: prompt_python.txt)"
```

## Тестирование

```python
from hh_auto_apply.infrastructure.browser.hh_client import HHClient

client = HHClient(cfg)
prompt_file = client._get_prompt_file()
# → data/prompt_python.txt (если search_query содержит "python")
```

## Миграция для пользователей

✅ **Нет необходимости менять конфигурацию.**
- Если у вас нет `.env` - система автоматически ищет промпты в `data/`
- Если у вас есть `AI_PROMPT_PATH` в `.env` - переименуйте на `AI_PROMPTS_DIR`

**Было:**
```dotenv
AI_PROMPT_PATH="prompt.txt"
```

**Стало:**
```dotenv
AI_PROMPTS_DIR="data"
```

## Технический долг исправлен ✓

- ✅ Правильное разделение между конфигурацией и логикой
- ✅ Динамическое определение промпта по типу поиска
- ✅ Fallback механизм для неизвестных типов поиска
- ✅ Подробные сообщения об ошибках при отсутствии промпта
- ✅ Консистентность с принципами Clean Architecture
