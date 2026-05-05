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

### Actual file inventory (as of current state)

```
run.py                          # Entry point (calls App directly).
hh_auto_apply/
  __init__.py                   # Empty package marker.
  app.py                        # Orchestrator (Zone A).
  client.py                     # 527-line god class (Zone A).
  config.py                     # Frozen dataclass + argparse helper (Zone A).
  domain.py                     # ApplyResult enum + Stats dataclass (Zone B-ish).
  persistence.py                # SeenRepo concrete-only (Zone A — no interface).
  selectors.py                  # CSS/XPath selectors (Zone B — clean).
  utils.py                      # human_pause + extract_vacancy_id (mostly clean).
tests/
  test_utils.py                 # Single test file. No conftest.py, no subfolders.
cover_letter.txt                # Static fallback cover letter.
prompt.txt                      # AI prompt template (read by client._generate_cover_letter).
requirements.txt
requirements-dev.txt
README.md
```

### Zone A — Legacy (DO NOT replicate this pattern, refactor when touching)

- **`hh_auto_apply/client.py`** — 527-line god class mixing browser navigation,
  resume selection logic, cover-letter form filling, OpenRouter HTTP calls,
  AI prompt loading, JSON response parsing, response token cleanup, and
  screenshot taking. Contains a **real bug**: duplicate `except TargetClosedError`
  branches (lines ~494 and ~501) — the second branch is unreachable.
- **`hh_auto_apply/app.py`** — orchestrator with inlined CSV writing
  (`_ensure_csv`, `_append_vacancy_to_csv`), `sys.exit(1)` on missing
  `cover_letter.txt`, `logger.add()` called inside `run()` instead of at boot,
  direct instantiation of `HHClient` and `SeenRepo`, broad `except Exception`
  in the main loop.
- **`hh_auto_apply/config.py`** — mostly fine as a settings container, but
  also defines `build_cli_cfg()` which mixes argparse with config loading.
  CLI parsing should live in `cli/args.py`, not in `config.py`.
- **`hh_auto_apply/persistence.py`** — `SeenRepo` is concrete-only, no
  interface, cannot be substituted in tests. Uses bare `except Exception`
  in `mark_seen` that silently swallows errors with a debug log.
- **`hh_auto_apply/utils.py`** — `human_pause(cfg: Config, ...)` imports
  `Config`, creating a backwards dependency from utils → config. A pure
  utility should not import the application's config object.

### Zone B — Target layered structure (ALWAYS use this pattern for new code)

Any new module must follow the structure described in **Architecture** below.
The closest existing things to a clean module are `hh_auto_apply/domain.py`
(small, focused, no I/O) and `hh_auto_apply/selectors.py` (data-only).

### Current tech stack (actual)

| Concern | Currently used | Target |
|---|---|---|
| Browser automation | `playwright` (sync API) | keep |
| HTTP client | `requests` ad-hoc, no retry, hardcoded inside `client.py` | `requests` + `tenacity` (already in `requirements.txt` — wire it up in a dedicated module) |
| Storage (seen-vacancy) | `sqlite3` raw, per-query connection | keep, but behind `ISeenRepo` interface |
| Configuration | `@dataclass(frozen=True)` + `python-dotenv` | keep — but split CLI parsing out |
| Logging | `loguru` configured inside `App.run()` | configure once in `core/logging.py`, called from `cli/main.py` before any `App` is instantiated |
| Error handling | `sys.exit(1)`, broad `except Exception`, swallowed exceptions | typed `AppError` hierarchy |
| Cover-letter generation | hardcoded OpenRouter call inside `client.py` (`_generate_cover_letter`) | abstract `ICoverLetterGenerator` + concrete impls in `infrastructure/ai/` |
| Vacancy description parsing | inlined in `client.py` (`_get_vacancy_description`) | belongs to `infrastructure/browser/` |
| CLI args | `argparse` inside `config.py` (`build_cli_cfg`) | extract to `cli/args.py` — config should not parse argv |
| Entry point | `run.py` at repo root | `python -m hh_auto_apply` via `cli/main.py` |
| Testing | `pytest`, single test file (`test_utils.py`) | add tests per layer (domain, repo, generator with mocks) |

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
    config.py            # Frozen dataclass loaded from env. NO business logic, NO argparse.
    exceptions.py        # AppError hierarchy: ConfigError, BrowserError, ...
    logging.py           # Loguru setup, called once at app boot.
  domain/
    __init__.py
    entities.py          # Vacancy, Resume, ApplyOutcome, Stats.
    rules.py             # Pure rules (e.g. ResumeMatcher) if/when needed.
  infrastructure/
    __init__.py
    browser/
      session.py         # Playwright BrowserContext lifecycle.
      hh_navigator.py    # Login check, search URL building, page navigation.
      hh_vacancy_page.py # Per-vacancy interactions (open, read description,
                         #   apply, fill letter, submit). Replaces client.py.
      selectors.py       # CSS / XPath selectors only — no logic.
    ai/
      generator.py       # ICoverLetterGenerator (Protocol or ABC).
      openrouter.py      # OpenRouter implementation, with tenacity retry.
      static.py          # Static-file fallback (reads cover_letter.txt).
      prompt_loader.py   # Reads and formats prompt.txt template.
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
  conftest.py            # Shared fixtures (does not exist yet — create on first test).
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
   also talk to OpenRouter. A class that parses a vacancy page does not also
   format an AI prompt.
6. **Selectors live in `selectors.py`.** Never hardcode a CSS selector inside
   business or navigation logic.
7. **No cross-feature imports** — `infrastructure.browser` must not import
   from `infrastructure.ai`, and vice versa.
8. **Utils stay pure.** `utils.py` (or its successor) must not import `Config`
   or any application-level type. If a helper needs settings, accept primitive
   parameters (e.g. `human_pause(min_s: float, max_s: float)`).

### Known violations to fix (do not replicate, fix when touching)

- **`client.py` mixes four layers** — Playwright navigation, resume-selection
  business logic, OpenRouter HTTP, and JSON-response post-processing all in
  one class. **Fix:** split into `HhNavigator`, `HhVacancyPage`,
  `OpenRouterGenerator`, `PromptLoader`, and a thin `ApplyOneVacancy` use case.
- **`client.py` has a duplicate `except TargetClosedError`** at lines ~494
  and ~501 — the second branch is unreachable and is a real bug. **Fix:**
  remove the duplicate and merge logic into a single handler.
- **`client._generate_cover_letter` cleans AI response with a chain of
  `.replace()` calls** for `<s>`, `</s>`, `[INST]`, `[/INST]`. **Fix:**
  extract `_strip_chat_tokens(text: str) -> str` and unit-test it.
- **`app.py` calls `sys.exit(1)`** for missing or empty `cover_letter.txt`.
  **Fix:** raise `ConfigError("cover_letter.txt missing or empty")`. Only
  `cli/main.py` is allowed to translate exceptions into exit codes.
- **`app.py` configures `loguru` inside `run()`** (`logger.remove()` +
  `logger.add()`). **Fix:** move to `core/logging.py::setup_logging(verbose)`
  and call from `cli/main.py` before constructing the use case.
- **`app.py` writes CSV inline** via `_ensure_csv` and `_append_vacancy_to_csv`.
  **Fix:** extract `CsvVacancySink` with `append(title, link)` method, inject
  into the use case. Header is written once at construction.
- **`app.py` catches broad `except Exception`** in the main loop and only
  logs. **Fix:** catch the specific `AppError` subclasses; let unknown
  exceptions bubble to `cli/main.py` for a single top-level handler.
- **`config.py` mixes argparse with config loading** in `build_cli_cfg`.
  **Fix:** move argparse into `cli/args.py`. `cli/main.py` merges CLI
  overrides into the env-based config via `dataclasses.replace`.
- **`tenacity` is in `requirements.txt` but unused.** **Fix:** wrap the
  OpenRouter call with `@retry` (exponential backoff, 3 attempts, retry only
  on `requests.exceptions.RequestException`).
- **`SeenRepo` opens a new connection per call.** Acceptable for SQLite
  single-thread use, but **fix:** add an `ISeenRepo` Protocol so tests can
  substitute an in-memory implementation.
- **`SeenRepo.mark_seen` swallows all exceptions** with a `logger.debug`.
  **Fix:** catch `sqlite3.Error` specifically and log at `WARNING` with the
  vacancy id.
- **`utils.human_pause(cfg: Config, ...)` imports `Config`.** **Fix:** change
  signature to `human_pause(min_s: float, max_s: float)` and let callers
  pass `cfg.min_sleep, cfg.max_sleep`.
- **`run.py` is the entry point but does its own DI.** **Fix:** replace
  contents with `from hh_auto_apply.cli.main import main; raise SystemExit(main())`,
  or remove in favor of a `python -m hh_auto_apply` invocation.

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
3. Prefer `pathlib.Path` over raw strings for paths (already done in
   `config.py`, keep it consistent).
4. Use `@dataclass(frozen=True)` for value objects, plain `@dataclass` for
   mutable state (e.g. `Stats`).
5. Prefer `Enum` / `StrEnum` over magic strings (already done with
   `ApplyResult`).
6. Avoid mutable default arguments. Use `field(default_factory=...)`.
7. Keep functions small. If a method has more than ~30 lines or three nested
   `try` blocks, split it.
8. Use f-strings for formatting; never `%` or `.format()` for new code.
9. Add docstrings (Google or reST style, pick one and stick with it) for
   every public class and function.
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
2. **Application use cases catch infrastructure exceptions and translate
   them** into `ApplyResult.ERROR` with a logged reason. They do not let
   exceptions propagate to the CLI loop unless the failure is fatal
   (e.g. config error).
3. **`cli/main.py` is the only place that calls `sys.exit()`.** Map specific
   exceptions to specific exit codes:
   - `ConfigError` → exit 2
   - `BrowserError` (fatal, e.g. Playwright not installed) → exit 3
   - Any other `AppError` → exit 1
4. **Never `except Exception: pass`.** If you swallow, log at `WARNING` with
   context. Empty `except` blocks are a code-review reject. The current
   `SeenRepo.mark_seen` is the canonical example to fix.
5. **For Playwright timeouts**, catch `playwright.sync_api.TimeoutError` and
   wrap in `BrowserError`. Same for `TargetClosedError`. Do not catch the
   same exception type twice (current bug in `client.apply_to_vacancy`).
6. **For HTTP**, catch `requests.exceptions.RequestException` and wrap in
   `CoverLetterError`. Use `tenacity.retry` to retry transient failures
   before giving up.

---

## Browser Automation (Playwright)

This is the largest source of complexity. Strict discipline required.

1. **Selectors live only in `infrastructure/browser/selectors.py`.** A grep
   for `data-qa=` or `:has-text(` anywhere else is a violation. Current
   `selectors.py` is already clean — keep it that way.
2. **Wrap Playwright calls in helper methods** that accept a `Page` and a
   selector — do not let `page.locator(...)` leak into business code.
3. **Always set `page.set_default_timeout()` once per page.** Do not pass
   timeouts inline to every locator call.
4. **Use `human_pause(...)` between user-visible actions.** Do not use raw
   `time.sleep()` outside of the helper itself.
5. **Always take a screenshot on a failure that involves UI state.** The
   path is determined by `cfg.screenshots_dir`. Screenshots are debug aids —
   do not read them back.
6. **Page lifecycle is owned by the use case.** The owning use case opens
   the page in a `try` block and closes it in `finally`. The current
   `apply_to_vacancy` mostly does this correctly (after several iterations),
   but the multiple removed `page.close()` calls scattered through error
   branches were a real bug — keep page lifecycle in exactly one place.
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
4. **Use `with self._conn() as c:`** (already done in `persistence.py`).
   Keep that pattern for any new SQLite code.
5. **Connections are short-lived.** Do not hold a connection as instance
   state.
6. **For HTTP integrations** (OpenRouter and any future provider):
   - Wrap the call with `tenacity.retry` (3 attempts, exponential backoff,
     min 1s, max 10s).
   - Always set a `timeout=` (currently 60s — keep that or lower).
   - Log the model name and duration at `INFO`; never log the API key or the
     full prompt at `INFO` (use `DEBUG` with a length-truncated payload).
   - The current `_generate_cover_letter` returns an empty string on error,
     forcing the caller to fall back silently. **Prefer:** raise
     `CoverLetterError` and let the use case decide between fallback and
     skip.

---

## Dependency Injection

This project does not need a DI container. Use constructor injection.

```python
# cli/main.py — the only place that wires dependencies
def main() -> int:
    args = parse_args()
    cfg = Config.from_env()
    cfg = apply_cli_overrides(cfg, args)

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
    session = RunSession(cfg=cfg, use_case=use_case, dry_run=args.dry_run)
    return session.run()
```

Rules:

1. Use cases and infrastructure classes accept their dependencies through
   `__init__`. Never look them up from a global.
2. The CLI is the only place that calls concrete constructors.
3. Tests construct use cases with fakes / mocks directly — no
   monkeypatching of imports.

---

## Configuration

The `Config` dataclass stays frozen and is loaded from environment variables
via `python-dotenv`.

Rules:

1. `Config.from_env()` is pure — given the same env, it returns the same
   value. No I/O beyond reading env vars.
2. **Move CLI argument parsing out of `config.py`.** `argparse` belongs in
   `cli/args.py`. `cli/main.py` then merges CLI overrides into the env-based
   config via `dataclasses.replace`.
3. **No business logic in `Config`.** It is a settings container only.
   If domain rules emerge (e.g. resume matching beyond a single string),
   put them in `domain/rules.py` as a dedicated class.
4. Validate at load time: required fields (e.g. `OPENROUTER_API_KEY` when
   `use_ai_cover_letter=True`) must raise `ConfigError` immediately, not
   silently default.
5. Sensitive values (API keys) must never be printed by `__repr__`.
   Override `__repr__` or use a custom `SecretStr` wrapper.

---

## Logging

Use `loguru` (already in use).

Rules:

1. **Configure logging once** in `core/logging.py` via a
   `setup_logging(verbose: bool)` function. Call it from `cli/main.py`
   before any `App` / use case is constructed. Do not call `logger.add()`
   anywhere else (current `app.py:run()` does — fix it).
2. **Levels:**
   - `DEBUG` — selector matches, network response sizes, internal state.
   - `INFO` — high-level progress (page N, vacancy opened, application sent).
   - `WARNING` — recoverable failures (resume not found, captcha suspected).
   - `ERROR` — non-recoverable for this vacancy (timeout, API error).
   - `SUCCESS` (loguru-specific) — successful application submitted.
3. **Never log secrets.** Not the `OPENROUTER_API_KEY`, not full prompts at
   `INFO`.
4. **Never log a full HTTP response body** unless at `DEBUG` and truncated.
5. **Use structured context** where it helps:
   `logger.bind(vacancy_id=vac_id).info("Applying")`.

---

## Persistence

1. **`SeenRepo` (SQLite)** — already correct in spirit. Keep `vacancy_id` as
   primary key. Add an `ISeenRepo` Protocol so tests can substitute an
   `InMemorySeenRepo`. Replace the bare `except Exception` in `mark_seen`
   with `except sqlite3.Error` and log at `WARNING`.
2. **CSV writes** — extract from `App` into `CsvVacancySink`. Open the file
   in append mode each call (current behavior is correct), but write the
   header only once at construction.
3. **Schema migrations** — none needed yet. If a column is added later,
   write a one-shot `ALTER TABLE` guarded by
   `try/except sqlite3.OperationalError`.
4. **Never access SQLite from the application or domain layers directly.**

---

## Testing Requirements

Current state: only `tests/test_utils.py` exists. There is no `conftest.py`,
no per-layer subfolders, and no fixtures.

Target state:

1. **Domain layer** — 100% covered. `extract_vacancy_id`, `Stats.bump`, any
   future `ResumeMatcher`. These are pure functions; no excuse not to test.
2. **Infrastructure** — test with fakes:
   - `SqliteSeenRepo` — use `:memory:` database.
   - `OpenRouterGenerator` — mock `requests.post` (use `responses` or
     `requests-mock`, or `monkeypatch`).
   - Browser code — do **not** start a real Chromium in unit tests. Use a
     fake `Page` object that records calls. Reserve real-Playwright tests
     for an `tests/integration/` directory with a `slow` mark.
3. **Application** — test use cases with all dependencies mocked.
4. **Test files mirror `hh_auto_apply/`:**
   `tests/domain/test_rules.py`,
   `tests/infrastructure/persistence/test_seen_repo.py`, etc.
5. **Use `pytest.fixture` for shared setup.** Place common fixtures in
   `tests/conftest.py` (create on first need).
6. **`bool` parameters in tests should use `parametrize`,** not duplicated
   tests.
7. **Every new public function must arrive with at least one test.**

---

## Code Review Expectations

1. Justify changes with SOLID, DRY, KISS — name the principle.
2. If refactoring, show the violation in a `# TODO(arch):` comment first,
   then commit the fix in a separate change.
3. Touching legacy code (`client.py`, `app.py`, `config.py`, `utils.py`,
   `persistence.py`): prefer to extract the smallest possible piece into the
   new structure. Do not rewrite the file in one go.
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
8. No selectors, SQL, or HTTP outside their designated infrastructure
   modules.

---

## Refactoring Existing Code Checklist

When asked to refactor a legacy file (`client.py`, `app.py`, `config.py`,
`utils.py`, `persistence.py`):

1. Identify the violation (mixed layers, broad `except`, missing
   abstraction, backwards import).
2. Mark it with `# TODO(arch): <description>` if not fixing now.
3. Fix one violation at a time. Do not rewrite unrelated code in the same
   commit.
4. When extracting from `client.py`:
   - Selectors are already in `selectors.py` — leave them there, just import
     from the new location after the package move.
   - Move browser navigation methods (`build_search_url`, `ensure_logged_in`,
     `list_vacancy_links_on_page`) into `infrastructure/browser/hh_navigator.py`.
   - Move per-vacancy interactions (`apply_to_vacancy`,
     `add_cover_letter_and_submit`, `select_specific_resume`,
     `fill_cover_letter_with_verification`) into
     `infrastructure/browser/hh_vacancy_page.py`.
   - Move OpenRouter HTTP (`_generate_cover_letter`) and prompt loading
     into `infrastructure/ai/openrouter.py` and
     `infrastructure/ai/prompt_loader.py`.
   - Move vacancy description parsing (`_get_vacancy_description`) into
     `hh_vacancy_page.py` — it's a Playwright concern, not AI.
   - Replace the call site in `client.py` with a delegation, or delete
     `client.py`'s method if it has no remaining callers.
5. When extracting from `config.py`:
   - `build_cli_cfg` → split into `cli/args.py::parse_args()` and
     `cli/main.py::apply_cli_overrides(cfg, args)`.
   - `Config` keeps only data, no behavior.
6. When extracting from `app.py`:
   - CSV helpers → `infrastructure/persistence/csv_sink.py::CsvVacancySink`.
   - `_read_cover_letter` → either
     `infrastructure/ai/static.py::StaticCoverLetterGenerator` or a small
     loader in `core/`.
   - The main `while` loop → `application/run_session.py::RunSession`.
   - Logging setup → `core/logging.py::setup_logging`.
7. When extracting from `utils.py`:
   - `human_pause` loses its `Config` parameter; callers pass primitives.
   - `extract_vacancy_id` is fine as-is; eventually move to `domain/`.
8. When extracting from `persistence.py`:
   - Add `ISeenRepo` Protocol; rename concrete class to `SqliteSeenRepo`.
   - Replace bare `except Exception` in `mark_seen` with
     `except sqlite3.Error` + `WARNING` log.
9. After every extraction, run the full test suite. If a test relied on the
   old shape, fix the test in the same commit and explain why in the message.

---

## Documentation Requirements

Project documentation lives in `docs/` (create on first use).

Rules:

1. **Do not create or update documentation unless explicitly requested.**
   This includes any `.md` files in `docs/`, ADRs, architecture guides,
   and updates to `README.md`. Only suggest documentation when the user
   asks for it.
2. The `README.md` is the single source of truth for user-facing setup.
3. Internal architectural decisions go in `docs/adr/NNNN-title.md` (one
   markdown file per decision) — only when explicitly requested.
4. API contracts for OpenRouter live in `docs/integrations/openrouter.md`
   if and when behavior diverges from upstream documentation — and only
   when explicitly requested.
5. Selectors are not "documentation" — they are code in `selectors.py`.
6. If information is missing, ask the user rather than assuming.

---

## Technology Stack

### Currently in use
- `playwright` — browser automation (sync API).
- `python-dotenv` — environment variable loading.
- `loguru` — logging.
- `requests` — HTTP client (used for OpenRouter inside `client.py`).
- `sqlite3` — standard library, used for seen-vacancy tracking.
- `pytest` — testing framework.

### Listed but not yet wired up
- `tenacity` — in `requirements.txt` but no `@retry` decorators in code.
  Wire it up around the OpenRouter call when extracting to
  `infrastructure/ai/openrouter.py`.

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

1. **Never create documentation files** unless explicitly requested by the
   user. This includes `.md` files in `docs/`, ADRs, and architecture
   guides. Only suggest documentation when user asks for it.
2. Generate production-ready Python code with type hints and docstrings.
3. Respect layer boundaries strictly: no Playwright in domain, no SQL in
   application, no business logic in config, no `Config` import in utils.
4. **Place all test files in `tests/` directory, mirroring the source
   structure.** Example: test for `hh_auto_apply/domain/rules.py` goes in
   `tests/domain/test_rules.py`. Never scatter test files across the
   codebase.
5. Never put a CSS selector outside `selectors.py`.
6. Never put `sys.exit()` outside `cli/main.py`.
7. Never swallow exceptions silently; always at least log at `WARNING` with
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
