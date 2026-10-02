# Директория Data

## CSV-файлы (результаты)

### vacancies.csv
Содержит успешно обработанные вакансии, на которые был отправлен отклик.
- **Столбцы:** title (название), link (ссылка), дата
- **Создаётся автоматически:** Да
- **Дополняется:** После успешного отклика

### vacancies_failed.csv
Содержит вакансии с ошибками или где отклик не был отправлен.
- **Столбцы:** title (название), link (ссылка), error_type (тип ошибки)
- **Создаётся автоматически:** Да
- **Дополняется:** После ошибки при отправке отклика

## Файлы ресурсов

### cover_letter.txt
Шаблон сопроводительного письма по умолчанию.
- **Формат:** Простой текст (UTF-8)
- **Использование:** Читается `App._read_cover_letter()` когда `use_ai_cover_letter=False`
- **Требуется:** Да, если `HH_USE_AI_COVER_LETTER=false` (по умолчанию)

### Промпты для писем

Три файла, по одному на каждое резюме на hh.ru. Нужный выбирается
автоматически по поисковому запросу из `.env` (`HH_SEARCH_QUERY`).

| Файл | Когда берётся | Под какое резюме |
|---|---|---|
| `prompt_flutter.txt` | в запросе есть «flutter» | Flutter разработчик |
| `prompt_fullstack.txt` | «fullstack», «full stack», «фулстек» | Fullstack разработчик |
| `prompt_php.txt` | «php», «laravel» | PHP и Laravel разработчик |

Порядок проверки важен: fullstack ищется раньше php, иначе запрос
«fullstack php» ушёл бы в php-промпт.

- **Формат:** простой текст, обязателен плейсхолдер `{job_description}`
- **Использование:** генерация сопроводительных писем через OpenRouter API
- **Можно задать вручную:** `AI_PROMPT_PATH=data/prompt_php.txt` в `.env`,
  это перебивает автовыбор

Факты о кандидате живут в самих промптах, в разделе «Профиль кандидата».
Менять опыт и цифры надо там, и сразу во всех трёх файлах, иначе письма
начнут противоречить друг другу.

### Python.txt
Примеры вопросов для Python-позиций.
- **Формат:** Простой текст с Q&A парами
- **Использование:** Справочный материал для понимания типов вопросов

### Flutter.txt
Примеры вопросов для Flutter-позиций.
- **Формат:** Простой текст с Q&A парами
- **Использование:** Справочный материал для понимания типов вопросов

## Использование

```python
# Загрузка из конфига
from hh_auto_apply.core.config import Config

cfg = Config.from_env()

# Доступ к путям CSV
print(cfg.vacancies_csv)        # "data/vacancies.csv"
print(cfg.failed_vacancies_csv) # "data/vacancies_failed.csv"

# Доступ к путям ресурсов
print(cfg.cover_letter_path)    # Path("data/cover_letter.txt")
print(cfg.ai_prompt_path)       # Path("data/prompt.txt")
```

## Переменные окружения

Настройка путей через .env:

```bash
HH_VACANCIES_CSV=data/vacancies.csv
HH_FAILED_VACANCIES_CSV=data/vacancies_failed.csv
AI_PROMPT_PATH=data/prompt.txt
```



