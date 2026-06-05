# hh_auto_apply

AI powered job application automation tool for hh.ru and LinkedIn.

The project automates vacancy discovery, application submission and personalized cover letter generation using browser automation and LLM models.

Built with Clean Architecture, Playwright automation and OpenRouter integration.

---

## Features

### Job Search Automation

* Automated vacancy discovery
* hh.ru application workflow
* LinkedIn Easy Apply support
* Vacancy filtering and matching
* Duplicate application prevention

### AI Features

* Personalized cover letter generation
* Vacancy analysis using LLMs
* Resume matching
* OpenRouter integration
* Custom prompt templates

### Automation

* Browser automation with Playwright
* Automatic form filling
* Session management
* Custom question handling
* Dry run mode

### Data Management

* SQLite storage
* Application history tracking
* CSV export and reporting
* Process monitoring

---

## Tech Stack

### Backend

* Python 3
* Playwright
* SQLite

### AI

* OpenRouter
* LLM Integration
* Prompt Engineering

### Architecture

* Clean Architecture
* Layered Architecture
* Domain Layer
* Application Layer
* Infrastructure Layer

### Testing

* pytest

---

## Architecture

```text
CLI
 │
 ▼
Application Layer
 │
 ▼
Domain Layer
 │
 ▼
Infrastructure Layer
 ├── Playwright
 ├── OpenRouter
 ├── SQLite
 └── External Platforms
      ├── hh.ru
      └── LinkedIn
```

---

## What This Project Demonstrates

* Python backend development
* Browser automation
* Playwright integration
* LLM integration
* Prompt engineering
* Clean Architecture
* Data persistence
* Automated testing
* CLI application development
* Third-party API integrations

---

## Installation

### Clone repository

```bash
git clone https://github.com/Zakirov-Yuriy/hh_auto_apply.git
cd hh_auto_apply
```

### Create virtual environment

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Install Playwright browsers

```bash
playwright install
```

---

## Configuration

The project is configured through a `.env` file.

### Main Settings

```dotenv
HH_SEARCH_QUERY="python разработчик"
HH_REGION_IDS="1,2"
HH_REMOTE_ONLY="true"
HH_MAX_APPLIES="100"
HH_RESUME_TITLE_MATCH="Python разработчик"
```

### Enable AI Cover Letters

```dotenv
USE_AI_COVER_LETTER="true"
```

### OpenRouter API Key

```dotenv
OPENROUTER_API_KEY="sk-or-v1-..."
```

### AI Model

```dotenv
AI_MODEL="mistralai/mistral-7b-instruct:free"
```

### Prompt Configuration

```dotenv
AI_PROMPT_PATH="prompt.txt"
```

The prompt file can be customized to generate cover letters in different styles and languages.

---

## Usage

Run hh.ru automation:

```bash
python run.py --platform hh
```

Run LinkedIn automation:

```bash
python run.py --platform linkedin
```

### Command Line Options

```bash
--headless
--dry-run
--verbose
--query "python developer"
```

Example:

```bash
python run.py --dry-run --verbose --query "Python Backend Developer"
```

---

## Project Structure

```text
hh_auto_apply/
├── core/
│   └── config.py
│
├── domain/
│   └── entities.py
│
├── infrastructure/
│   ├── browser/
│   │   ├── hh_client.py
│   │   └── selectors.py
│   ├── ai/
│   ├── persistence/
│   └── utils.py
│
├── application/
│   └── run_session.py
│
├── cli/
│   ├── main.py
│   └── args.py
│
├── docs/
├── tests/
└── run.py
```

---

## Documentation

| Document                       | Description               |
| ------------------------------ | ------------------------- |
| docs/INDEX.md                  | Documentation index       |
| docs/ARCHITECTURE.md           | Architecture overview     |
| docs/CUSTOM_QUESTIONS.md       | Custom questions handling |
| docs/CUSTOM_QUESTIONS_READY.md | Ready-to-use solutions    |
| data/README.md                 | Resources and templates   |
| tests/README.md                | Testing guide             |

---

## Testing

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run tests:

```bash
pytest tests/ -v
```

Run tests with coverage:

```bash
pytest tests/ --cov=hh_auto_apply --cov-report=html
```

---

## Author

**Yuriy Zakirov**

Python Backend Developer

GitHub: https://github.com/Zakirov-Yuriy

Telegram: @Zak_Yuri
