# Data Directory

## CSV Files (Results)

### vacancies.csv
Contains successfully processed vacancies where the application was submitted.
- **Columns:** title, link
- **Auto-created:** Yes, if missing
- **Auto-appended:** On successful application

### vacancies_failed.csv
Contains vacancies with errors or where application failed.
- **Columns:** title, link, error_type
- **Auto-created:** Yes, if missing
- **Auto-appended:** On application failure

## Resource Files

### cover_letter.txt
Standard cover letter template.
- **Format:** Plain text (UTF-8)
- **Usage:** Read by `App._read_cover_letter()` when `use_ai_cover_letter=False`
- **Required:** Yes, if `HH_USE_AI_COVER_LETTER=false` (default)

### prompt_python.txt
AI prompt template for Python vacancies.
- **Format:** Plain text with placeholders
- **Usage:** Used to generate cover letters via OpenRouter API
- **Placeholder:** `{company_name}`, `{position}`, etc.

### prompt_flutter.txt
AI prompt template for Flutter vacancies.
- **Format:** Plain text with placeholders
- **Usage:** Used to generate cover letters via OpenRouter API

### Python.txt
Example questions for Python positions.
- **Format:** Plain text with Q&A pairs
- **Usage:** Reference for understanding question patterns

### Flutter.txt
Example questions for Flutter positions.
- **Format:** Plain text with Q&A pairs
- **Usage:** Reference for understanding question patterns

## Usage

```python
# Loading from Config
from hh_auto_apply.core.config import Config

cfg = Config.from_env()

# Access CSV paths
print(cfg.vacancies_csv)        # "data/vacancies.csv"
print(cfg.failed_vacancies_csv) # "data/vacancies_failed.csv"

# Access resource paths
print(cfg.cover_letter_path)    # Path("data/cover_letter.txt")
print(cfg.ai_prompt_path)       # Path("data/prompt.txt")
```

## Environment Variables

Configure paths via .env:

```bash
HH_VACANCIES_CSV=data/vacancies.csv
HH_FAILED_VACANCIES_CSV=data/vacancies_failed.csv
AI_PROMPT_PATH=data/prompt.txt
```

## Note

All CSV and text files are read/written as UTF-8 encoded.
