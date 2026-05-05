# AI-Powered Custom Questions Handling

## Overview

The bot now automatically detects and fills custom question fields in HH.ru vacancy response forms using AI-generated answers.

## How It Works

### 1. Detection (`_detect_custom_questions`)
- Scans the response form for textarea fields with names matching pattern `task_*_text`
- Attempts to extract the question text from associated labels, legends, or parent elements
- Falls back to default message if question text cannot be found

### 2. Context Extraction (`_extract_resume_context`)
- Extracts resume information from the page:
  - Job title
  - Salary expectation
  - Experience years
  - Skills
  - Education level
- Uses defaults if extraction fails

### 3. AI Response Generation (`_generate_answers_for_custom_questions`)
- Calls OpenRouter API with `openai/gpt-oss-120b:free` model
- Generates contextually appropriate answers based on:
  - Resume data (salary, experience, skills)
  - Vacancy title
  - Question text
- Supports API key rotation if multiple keys are configured
- Retries on failure with key switching

### 4. Form Filling (`_fill_custom_questions`)
- Fills textarea fields with AI-generated answers
- Validates that text was successfully entered
- Handles multiple fields in sequence

### 5. Integration (`apply_to_vacancy`)
- Called automatically after form modal opens
- Processes custom questions before standard form submission
- Non-blocking: continues with standard process if custom questions processing fails

## Configuration

Add to your `.env` file:

```env
# AI Cover Letter Generation
USE_AI_COVER_LETTER=true
AI_MODEL=openai/gpt-oss-120b:free
OPENROUTER_API_KEY=your-api-key-here

# Optional: Multiple API keys for rotation
OPENROUTER_API_KEYS=key1,key2,key3
```

## Testing

### Unit Tests
```bash
pytest tests/test_client_custom_questions.py -v
```

### Integration Test (Manual)
```bash
python test_custom_questions_debug.py
```

This will:
1. Open a test vacancy in a headless browser
2. Click "Откликнуться" button
3. Detect custom questions
4. Generate AI answers
5. Fill the form
6. Save a screenshot to `debug_custom_form.png`

## Supported Question Types

### Salary Questions
Detected by keywords: "зарплат", "ожидани"
- Generates answer with salary amount + Gross/Net specification
- Example: "130 000 рублей Net (после вычета налога)"

### Motivation/Interest Questions
- Generates contextual explanation based on resume data
- References job title, experience, skills
- Mentions company/position interest

### General Questions
- Generates professional responses based on resume context
- Adapts to question content when possible

## Error Handling

- **API Failures**: Logs warning and retries with next API key
- **Parsing Failures**: Falls back to default questions structure
- **Missing Information**: Uses sensible defaults for resume context
- **Form Filling Failures**: Logs warning but continues with standard process

## Performance

- Question detection: ~50ms
- Context extraction: ~100ms
- AI response generation: ~8-10 seconds per question (API latency)
- Form filling: ~1 second per field

Total per-vacancy overhead: ~10-20 seconds for 2-3 custom questions

## Known Limitations

1. Question text extraction depends on HTML structure - may not work for all companies' custom forms
2. AI responses are generated; quality depends on model capability
3. No support for multi-choice or other field types - only textarea
4. Form labels must be properly structured for extraction to work

## Debugging

Enable debug logging to see detailed information:

```python
from loguru import logger
logger.enable("hh_auto_apply")
logger.level("DEBUG")
```

Key debug messages:
- `Обнаружено N кастомных textarea полей` - Number of custom fields found
- `Найден вопрос: field_name -> question_text` - Successfully extracted question
- `Генерирую ответ на вопрос в field_name` - Generating response
- `Ответ на вопрос field_name сгенерирован: answer_text` - Response generated
- `Поле field_name успешно заполнено` - Field filled successfully
