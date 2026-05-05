# Copilot Instructions — hh_auto_apply Project

## Role

Act as Senior Python Developer and technical mentor.
Write clean, testable, production-ready code for a CLI automation tool
that runs on Linux, macOS, and Windows.

Primary goal is long-term maintainable architecture using layered design,
explicit dependencies, and typed contracts.

---

## Current Project State (read before generating any code)

This project is a CLI utility that automates job applications on hh.ru using
**Playwright** (browser automation), **SQLite** (seen-vacancy tracking),
and **OpenRouter** (AI cover-letter generation). It is in **active migration**
from a script-style layout toward a properly layered Python application.

Before generating code, identify which zone the target file is in and follow
the appropriate rules.

### Zone A — Legacy (DO NOT replicate this pattern, refactor when touching)
- `hh_auto_apply/client.py` — 550-line god class mixing browser navigation,
  HTTP calls, AI prompting, UI parsing, resume-selection logic, and screenshots.
- `hh_auto_apply/config.py` — configuration dataclass with embedded business
  rules (`RESUME_KEYWORDS_MAP`, `get_resume_match_for_vacancy`,
  `get_resume_search_patterns`). Config should hold settings, not domain logic.
- `hh_auto_apply/app.py` — orchestrator with inlined CSV writing, `sys.exit(1)`
  on missing files, and direct instantiation of `HHClient`.
- `hh_auto_apply/persistence.py` — `SeenRepo` is concrete-only, no interface,
  cannot be substituted in tests.

### Zone B — Target layered structure (ALWAYS use this pattern for new code)
Any new module must follow the structure described in **Architecture** below.
The closest existing thing to a clean module is `hh_auto_apply/utils.py` and
`hh_auto_apply/domain.py` — small, focused, no side effects.

### Current tech stack (actual)

| Concern | Currently used | Target |
|---|---|---|
| Browser automation | `playwright` (sync API) | keep |
| HTTP client | `requests` ad-hoc, no retry | `requests` + `tenacity` (already in `requirements.txt` — wire it up) |
| Storage (seen-vacancy) | `sqlite3` raw, per-query connection | keep, but behind `ISeenRepo` interface |
| Configuration | `@dataclass(frozen=True)` + `python-dotenv` | keep — but split business rules out |
| Logging | `loguru` | keep, configure once in `core/logging.py` |
| Error handling | `sys.exit(1)`, broad `except Exception` | typed `AppError` hierarchy |
| Cover-letter generation | hardcoded OpenRouter call inside `client.py` | abstract `CoverLetterGenerator` + concrete impls |
| CLI args | `argparse` in `config.py` | extract to `cli/args.py` — config should not parse argv |
| Testing | `pytest`, one util test | add tests per layer (domain, repo, generator with mocks) |

---

## Priorities

1. Correctness, predictable behavior, no silent failures.
2. Layered architecture — low coupling, explicit dependencies.
3. Testability — every non-trivial unit must be reachable by `pytest` without
   spinning up a real browser or hitting a real API.
4. DRY and KISS — minimize complexity and duplication.
5. Always document non-obvious decisions, especially around UI selectors,
   timing, and retry policy.

---

## Architecture

### Target: layered Python application

```
hh_auto_apply/
  core/
    __init__.py
    config.py            # Frozen dataclass loaded from env. NO business logic.
    exceptions.py        # AppError hierarchy: ConfigError, BrowserError, ...
    logging.py           # Loguru setup, called once at app boot.
  domain/
    __init__.py
    entities.py          # Vacancy, Resume, ApplyOutcome, Stats.
    rules.py             # Resume-matching rules (formerly in Config).
  infrastructure/
    __init__.py
    browser/
      session.py         # Playwright BrowserContext lifecycle.
      hh_navigator.py    # Login check, search URL building, page navigation.
      hh_vacancy_page.py # Per-vacancy interactions (apply, fill letter, submit).
      selectors.py       # CSS / XPath selectors only — no logic.
    ai/
      generator.py       # ICoverLetterGenerator (abstract).
      openrouter.py      # Concrete OpenRouter implementation, with tenacity retry.
      static.py          # Concrete static-file fallback (reads cover_letter.txt).
    persistence/
      seen_repo.py       # ISeenRepo + SqliteSeenRepo.
      csv_sink.py        # Append-only CSV writer for successful applies.
  application/
    __init__.py
    apply_one_vacancy.py # Use case: open URL, decide, apply, persist.
    run_session.py       # Top-level loop (replaces current app.py).
  cli/
    __init__.py
    args.py              # argparse — pure parsing, returns a typed namespace.
    main.py              # Entry point — wires dependencies and calls run_session.
tests/
  domain/
  infrastructure/
  application/
  conftest.py            # Shared fixtures.
```

### Architecture Rules

1. **Domain layer must not import from `infrastructure/` or `application/`.**
   Entities and rules are pure Python, no Playwright, no requests, no SQLite.
2. **Infrastructure implements domain contracts** (interfaces defined as
   `abc.ABC` or `typing.Protocol` inside `domain/` or alongside the impl).
3. **Application layer depends only on domain interfaces.** It receives
   concrete implementations through constructor injection from `cli/main.py`.
4. **CLI is the only place that wires everything together.** `cli/main.py`
   constructs concrete classes (`SqliteSeenRepo`, `OpenRouterGenerator`, etc.)
   and passes them into the application layer.
5. **One responsibility per class.** A class that talks to Playwright does not
   also talk to OpenRouter.
6. **Selectors live in `selectors.py`.** Never hardcode a CSS selector inside
   business or navigation logic.
7. **No cross-feature imports** — `infrastructure.browser` must not import
   from `infrastructure.ai`, and vice versa.

### Known violations to fix (do not replicate, fix when touching)

- **`client.py` mixes layers** — Playwright + `requests` + business rules in
  one class. **Fix:** split into `HhNavigator`, `HhVacancyPage`,
  `OpenRouterGenerator`, and a thin `ApplyOneVacancy` use case.
- **`config.py` contains domain logic** (`RESUME_KEYWORDS_MAP`,
  `get_resume_match_for_vacancy`). **Fix:** move to `domain/rules.py` as a
  `ResumeMatcher` class. `Config` only holds values, not behavior.
- **`app.py` calls `sys.exit(1)`** for missing `cover_letter.txt`. **Fix:**
  raise `ConfigError("cover_letter.txt missing or empty")`. Only `cli/main.py`
  is allowed to translate exceptions into exit codes.
- **`client.py` has duplicate `except TargetClosedError`** (real bug — the
  second branch is unreachable). **Fix:** remove the duplicate and merge logic.
- **`tenacity` is in `requirements.txt` but unused.** **Fix:** wrap the
  OpenRouter call with `@retry` (exponential backoff, 3 attempts, retry only
  on `requests.exceptions.RequestException`).
- **`SeenRepo` opens a new connection per call.** Acceptable for SQLite single
  thread, but **fix:** add an `ISeenRepo` Protocol so tests can substitute an
  in-memory implementation.
- **CSV writing is inlined in `App`.** **Fix:** extract `CsvVacancySink` with
  `append(title, link)` method, inject into the use case.

---

## Development Principles

Follow Clean Code, SOLID, DRY, KISS, YAGNI, separation of concerns,
composition over inheritance, fail-fast validation.

SOLID requirements:

1. Single responsibility per class — Playwright code, HTTP code, and SQLite
   code never live together.
2. Open for extension — new cover-letter providers added by implementing
   `ICoverLetterGenerator`, not by editing existing classes.
3. Liskov — subclasses must honor the same exception contract.
4. Interface segregation — split big interfaces; e.g. don't make `HhClient`
   one interface, split into `IVacancyLister`, `IVacancyApplier`.
5. Depend on abstractions — `ApplyOneVacancy` accepts `ICoverLetterGenerator`,
   never `OpenRouterGenerator` directly.

---

## Code Style

1. Use explicit type hints on all public functions and class attributes.
2. Use `from __future__ import annotations` at the top of every module.
3. Prefer `pathlib.Path` over raw strings for paths (already done in `config.py`,
   keep it consistent).
4. Use `@dataclass(frozen=True)` for value objects, plain `@dataclass` for
   mutable state (e.g. `Stats`).
5. Prefer `Enum` / `StrEnum` over magic strings (already done with `ApplyResult`).
6. Avoid mutable default arguments. Use `field(default_factory=...)`.
7. Keep functions small. If a method has more than ~30 lines or three nested
   `try` blocks, split it.
8. Use f-strings for formatting; never `%` or `.format()` for new code.
9. Add docstrings (Google or reST style, pick one and stick with it) for every
   public class and function.
10. Comment **why**, not **what**. The "what" should be obvious from the code.
11. PEP 8 compliance via `ruff` or `black` — line length 100, not 79.

---

## Error Handling

Use a typed exception hierarchy in `core/exceptions.py`:

```python
class AppError(Exception):
    """Base exception for the application."""


class ConfigError(AppError):
    """Configuration is missing or invalid."""


class BrowserError(AppError):
    """Playwright-level failure (timeout, target closed, navigation)."""


class CoverLetterError(AppError):
    """Cover letter could not be obtained (AI failure or empty file)."""


class PersistenceError(AppError):
    """SQLite or CSV write failure."""


class ApplyError(AppError):
    """Failed to submit the application form (captcha, missing fields, etc.)."""
```

Rules:

1. **Infrastructure modules raise typed `AppError` subclasses.** Never raise
   bare `Exception` or `RuntimeError` from infrastructure.
2. **Application use cases catch infrastructure exceptions and translate them
   into `ApplyResult.ERROR` with a logged reason.** They do not let exceptions
   propagate to the CLI loop unless the failure is fatal (e.g. config error).
3. **`cli/main.py` is the only place that calls `sys.exit()`.** Map specific
   exceptions to specific exit codes:
   - `ConfigError` → exit 2
   - `BrowserError` (fatal, e.g. Playwright not installed) → exit 3
   - Any other `AppError` → exit 1
4. **Never `except Exception: pass`.** If you swallow, log at WARNING with
   context. Empty `except` blocks are a code-review reject.
5. **For Playwright timeouts**, catch `playwright.sync_api.TimeoutError` and
   wrap in `BrowserError`. Same for `TargetClosedError`.
6. **For HTTP**, catch `requests.exceptions.RequestException` and wrap in
   `CoverLetterError`. Use `tenacity.retry` to retry transient failures
   before giving up.

---

## Browser Automation (Playwright)

This is the largest source of complexity. Strict discipline required.

1. **Selectors live only in `infrastructure/browser/selectors.py`.** A grep
   for `data-qa=` or `:has-text(` anywhere else is a violation.
2. **Wrap Playwright calls in helper methods** that accept a `Page` and a
   selector — do not let `page.locator(...)` leak into business code.
3. **Always set `page.set_default_timeout()` once per page.** Do not pass
   timeouts inline to every locator call.
4. **Use `human_pause()` (already in `utils.py`) between user-visible actions.**
   Do not use raw `time.sleep()` outside of `utils.py`.
5. **Always take a screenshot on a failure that involves UI state.** The path
   is determined by `cfg.screenshots_dir`. Screenshots are debug aids — do not
   read them back.
6. **Never close a `Page` from inside a use case.** The owning use case opens
   the page, and the same use case closes it in `finally`. Avoid the bug
   currently present in `client.apply_to_vacancy` where multiple paths used to
   close the page.
7. **Login is interactive (CLI prompt).** Do not automate password entry —
   it's against ToS and breaks captcha. Keep `input()` only for this case.

---

## Data Layer

For new infrastructure code:

1. **Define an interface (abstract base class or `Protocol`)** in the same
   package. Example:

   ```python
   from typing import Protocol

   class ISeenRepo(Protocol):
       def is_seen(self, vacancy_id: str) -> bool: ...
       def mark_seen(self, vacancy_id: str) -> None: ...
       def cleanup(self, ttl_days: int) -> None: ...
   ```

2. **Concrete implementations end with the technology suffix:**
   `SqliteSeenRepo`, `CsvVacancySink`, `OpenRouterGenerator`.
3. **Use parameterized SQL.** Never f-string a value into a SQL statement.
4. **Use `with self._conn() as c:` (already done in `persistence.py`).**
   Keep that pattern for any new SQLite code.
5. **Connections are short-lived.** Do not hold a connection as instance state.
6. **For HTTP integrations** (OpenRouter and any future provider):
   - Wrap the call with `tenacity.retry` (3 attempts, exponential backoff,
     min 1s, max 10s).
   - Always set a `timeout=` (currently 60s — keep that or lower).
   - Log the model name and duration at INFO; never log the API key or the
     full prompt at INFO (use DEBUG with a length-truncated payload).

---

## Dependency Injection

This project does not need a DI container. Use constructor injection.

```python
# cli/main.py — the only place that wires dependencies
def main() -> int:
    cfg = Config.from_env()
    setup_logging(verbose=cfg.verbose)

    seen_repo = SqliteSeenRepo(cfg.db_path)
    csv_sink = CsvVacancySink(cfg.vacancies_csv)
    cover_letter_gen = (
        OpenRouterGenerator(api_key=cfg.openrouter_api_key,
                            model=cfg.ai_model,
                            prompt_path=cfg.ai_prompt_path)
        if cfg.use_ai_cover_letter and cfg.openrouter_api_key
        else StaticCoverLetterGenerator(cfg.cover_letter_path)
    )

    use_case = ApplyOneVacancy(
        navigator=HhNavigator(cfg),
        vacancy_page=HhVacancyPage(cfg),
        cover_letter_gen=cover_letter_gen,
        seen_repo=seen_repo,
        csv_sink=csv_sink,
    )
    session = RunSession(cfg=cfg, use_case=use_case)
    return session.run()
```

Rules:

1. Use cases and infrastructure classes accept their dependencies through
   `__init__`. Never look them up from a global.
2. The CLI is the only place that calls concrete constructors.
3. Tests construct use cases with fakes / mocks directly — no monkeypatching
   of imports.

---

## Configuration

The `Config` dataclass stays frozen and is loaded from environment variables
via `python-dotenv`.

Rules:

1. `Config.from_env()` is pure — given the same env, it returns the same
   value. No I/O beyond reading env vars.
2. **Move CLI argument parsing out of `config.py`.** `argparse` belongs in
   `cli/args.py`. The function in `cli/main.py` then merges CLI overrides
   into the env-based config via `dataclasses.replace`.
3. **No business logic in `Config`.** `RESUME_KEYWORDS_MAP` and
   `get_resume_match_for_vacancy` belong in `domain/rules.py` as a
   `ResumeMatcher` class.
4. Validate at load time: required fields (e.g. `OPENROUTER_API_KEY` when
   `use_ai_cover_letter=True`) must raise `ConfigError` immediately, not
   silently default.
5. Sensitive values (API keys) must never be printed by `__repr__`.
   Override `__repr__` or use a custom `SecretStr` wrapper.

---

## Logging

Use `loguru` (already in use).

Rules:

1. **Configure logging once** in `core/logging.py` via a `setup_logging(verbose: bool)`
   function. Call it from `cli/main.py`. Do not call `logger.add()` outside
   of this setup.
2. **Levels:**
   - `DEBUG` — selector matches, network response sizes, internal state.
   - `INFO` — high-level progress (page N, vacancy opened, application sent).
   - `WARNING` — recoverable failures (resume not found, captcha suspected).
   - `ERROR` — non-recoverable for this vacancy (timeout, API error).
   - `SUCCESS` (loguru-specific) — successful application submitted.
3. **Never log secrets.** Not the `OPENROUTER_API_KEY`, not full prompts at INFO.
4. **Never log a full HTTP response body** unless at DEBUG and truncated.
5. **Use structured context** where it helps:
   `logger.bind(vacancy_id=vac_id).info("Applying")`.

---

## Persistence

1. **`SeenRepo` (SQLite)** — already correct in spirit. Keep `vacancy_id` as
   primary key. Add an `ISeenRepo` Protocol so tests can substitute an
   `InMemorySeenRepo`.
2. **CSV writes** — extract from `App` into `CsvVacancySink`. Open the file
   in append mode each call (current behavior is correct), but write a header
   only once at construction.
3. **Schema migrations** — none needed yet. If a column is added later,
   write a one-shot `ALTER TABLE` guarded by `try/except sqlite3.OperationalError`.
4. **Never access SQLite from the application or domain layers directly.**

---

## Testing Requirements

1. **Domain layer** — 100% covered. `ResumeMatcher`, `extract_vacancy_id`,
   `Stats.bump`. These are pure functions; no excuse not to test.
2. **Infrastructure** — test with fakes:
   - `SqliteSeenRepo` — use `:memory:` database.
   - `OpenRouterGenerator` — mock `requests.post` (use `responses` or
     `requests-mock`, or `monkeypatch`).
   - Browser code — do **not** start a real Chromium in unit tests. Use a
     fake `Page` object that records calls. Reserve real-Playwright tests
     for an `tests/integration/` directory with a `slow` mark.
3. **Application** — test use cases with all dependencies mocked.
4. **Test files mirror `hh_auto_apply/`:**
   `tests/domain/test_rules.py`, `tests/infrastructure/persistence/test_seen_repo.py`,
   etc.
5. **Use `pytest.fixture` for shared setup.** Place common fixtures in
   `tests/conftest.py`.
6. **`bool` parameters in tests should use `parametrize`,** not duplicate
   tests.
7. **Every new public function must arrive with at least one test.**

---

## Code Review Expectations

1. Justify changes with SOLID, DRY, KISS — name the principle.
2. If refactoring, show the violation in a `# TODO(arch):` comment first,
   then commit the fix in a separate change.
3. Touching legacy code (`client.py`, `app.py`, `config.py` business logic):
   prefer to extract the smallest possible piece into the new structure.
   Do not rewrite the file in one go.
4. Prefer clarity over cleverness. List comprehensions over `reduce`,
   explicit loops over chained generator expressions when state is involved.
5. Run `python -m pytest` and `python -m ruff check hh_auto_apply` before
   submitting. Both must be clean.

---

## New Module Checklist

Before merging a new feature module:

1. Module placed in the correct layer (`core/`, `domain/`, `infrastructure/`,
   `application/`, `cli/`).
2. Public API documented with docstrings.
3. Type hints on all public functions.
4. Interfaces (`Protocol` or `ABC`) defined where another implementation is
   foreseeable.
5. Wired into `cli/main.py` if user-facing.
6. Tests added in the mirror path under `tests/`.
7. `requirements.txt` updated if a new dependency is introduced — and that
   dependency is justified in the PR description.
8. No selectors, SQL, or HTTP outside their designated infrastructure modules.

---

## Refactoring Existing Code Checklist

When asked to refactor a legacy file (`client.py`, `app.py`, `config.py`):

1. Identify the violation (mixed layers, business logic in config, broad
   `except`, missing abstraction).
2. Mark it with `# TODO(arch): <description>` if not fixing now.
3. Fix one violation at a time. Do not rewrite unrelated code in the same
   commit.
4. When extracting from `client.py`:
   - Move the related selectors to `selectors.py` first (they are already there).
   - Move the method into a new class in `infrastructure/browser/`.
   - Replace the call site in `client.py` with a delegation, or delete
     `client.py`'s method if it has no remaining callers.
5. When extracting from `config.py`:
   - Resume-matching helpers go to `domain/rules.py` as a `ResumeMatcher`.
   - `Config` keeps only data, no behavior.
6. After every extraction, run the full test suite. If a test relied on the
   old shape, fix the test in the same commit and explain why in the message.

---

## Documentation Requirements

Project documentation lives in `docs/` (create on first use).

Rules:

1. Do not create or update documentation unless explicitly requested.
2. The `README.md` is the single source of truth for user-facing setup.
3. Internal architectural decisions go in `docs/adr/NNNN-title.md` (one
   markdown file per decision).
4. API contracts for OpenRouter live in `docs/integrations/openrouter.md`
   if and when behavior diverges from upstream documentation.
5. Selectors are not "documentation" — they are code in `selectors.py`.
6. If information is missing, ask the user rather than assuming.

---

## Technology Stack

### Currently in use
- `playwright` — browser automation (sync API).
- `python-dotenv` — environment variable loading.
- `loguru` — logging.
- `requests` — HTTP client (used for OpenRouter).
- `tenacity` — retry library (in `requirements.txt`, **currently not wired up**).
- `sqlite3` — standard library, used for seen-vacancy tracking.
- `pytest` — testing framework.

### To add when extracting / refactoring
- `ruff` — linter and formatter (replaces flake8 + black for new code).
- `mypy` — static type checker, run in CI.
- `requests-mock` or `responses` — for testing the OpenRouter integration.

### Possible future additions (do not add until needed)
- `httpx` — only if async HTTP is needed; keep `requests` for now.
- `pydantic` — only if config validation grows beyond what `dataclass` +
  manual checks can handle.

---

## General Copilot Behavior

1. **Never create documentation files** unless explicitly requested by the user.
   This includes `.md` files in `docs/`, ADRs, and architecture guides.
   Only suggest documentation when user asks for it.
2. Generate production-ready Python code with type hints and docstrings.
3. Respect layer boundaries strictly: no Playwright in domain, no SQL in
   application, no business logic in config.
4. **Place all test files in `tests/` directory, mirroring the source structure.**
   Example: test for `hh_auto_apply/domain/rules.py` goes in
   `tests/domain/test_rules.py`. Never scatter test files across the codebase.
5. Never put a CSS selector outside `selectors.py`.
6. Never put `sys.exit()` outside `cli/main.py`.
7. Never swallow exceptions silently; always at least log at WARNING with
   context.
8. Prefer composition over inheritance; pass dependencies in `__init__`.
9. Generate testable code: any class that touches the network or filesystem
   must be reachable behind a `Protocol`.
10. Keep consistency with existing patterns — frozen dataclass for config,
    loguru for logs, `human_pause` for delays.
11. When generating code for a legacy file, note any architectural violation
    present in a `# TODO(arch):` comment and suggest the fix even if not
    implementing it now.
12. Always check which zone (A or B) the target file belongs to before
    generating code.
