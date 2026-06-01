"""Core configuration module for hh_auto_apply application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    # Площадка поиска работы: "hh" или "linkedin".
    platform: str = "hh"
    # Текстовая локация для LinkedIn (region_ids от hh там не работают).
    # Например: "Russia", "Remote", "Germany". Пусто = без фильтра по локации.
    linkedin_location: str = ""

    search_query: str = "python"
    region_ids: List[str] | None = None
    remote_only: bool = False
    max_applies: int = 200
    min_sleep: float = 3.0
    max_sleep: float = 7.0
    persist_dir: str = ".hh_user"
    screenshots_dir: str = "screenshots"
    db_path: str = "hh_seen.sqlite"
    seen_ttl_days: int = 14
    resume_match: str = "python разработчик"  # нижний регистр
    fail_if_resume_not_found: bool = True
    require_cover_letter: bool = True
    cover_letter_path: Path = Path("data/cover_letter.txt")
    base_url: str = "https://hh.ru"
    max_pages: int = 100
    empty_pages_tolerance: int = 3
    headless: bool = False
    slow_mo_ms: int = 50
    verbose: bool = False
    vacancies_csv: str = "data/vacancies.csv"
    failed_vacancies_csv: str = "data/vacancies_failed.csv"
    use_ai_cover_letter: bool = False
    openrouter_api_keys: List[str] | None = None
    ai_prompts_dir: Path = Path("data")  # Директория с файлами промптов
    ai_model: str = "openai/gpt-oss-120b:free"
    # HH API настройки для получения структурированных данных вакансии
    use_hh_api_first: bool = True
    hh_api_user_agent: str = "ZakirovCoverLetter/1.0 (zak.yuri@yandex.ru)"
    # Стоп-слова для фильтрации вакансий по названию
    stop_words: List[str] | None = None

    @staticmethod
    def from_env() -> "Config":
        """Load configuration from environment variables."""
        from dotenv import load_dotenv

        load_dotenv()

        region_ids = [r.strip() for r in os.getenv("HH_REGION_IDS", "").split(",") if r.strip()]
        vacancies_csv = os.getenv("HH_VACANCIES_CSV") or os.getenv("HH_COMPANIES_CSV") or "data/vacancies.csv"
        failed_vacancies_csv = os.getenv("HH_FAILED_VACANCIES_CSV", "data/vacancies_failed.csv")
        api_keys_str = os.getenv("OPENROUTER_API_KEY", "").strip()
        openrouter_api_keys = [k.strip() for k in api_keys_str.split(",") if k.strip()] if api_keys_str else []

        stop_words_str = os.getenv("HH_STOP_WORDS", "").strip()
        stop_words = [w.strip() for w in stop_words_str.split(",") if w.strip()] if stop_words_str else []

        platform = os.getenv("PLATFORM", "hh").strip().lower()

        # У каждой площадки своя папка сессии браузера (разные cookies/логин),
        # если пользователь явно не задал HH_PERSIST_DIR.
        default_persist = ".linkedin_user" if platform in ("linkedin", "li") else ".hh_user"
        persist_dir = os.getenv("HH_PERSIST_DIR", default_persist)

        return Config(
            platform=platform,
            linkedin_location=os.getenv("LINKEDIN_LOCATION", "").strip(),
            search_query=os.getenv("HH_SEARCH_QUERY", "python").strip(),
            region_ids=region_ids or [],
            remote_only=os.getenv("HH_REMOTE_ONLY", "false").lower() == "true",
            max_applies=int(os.getenv("HH_MAX_APPLIES", "200")),
            min_sleep=float(os.getenv("HH_MIN_SLEEP", "3")),
            max_sleep=float(os.getenv("HH_MAX_SLEEP", "7")),
            persist_dir=persist_dir,
            screenshots_dir=os.getenv("HH_SCREENSHOTS_DIR", "screenshots"),
            db_path=os.getenv("HH_DB_PATH", "hh_seen.sqlite"),
            seen_ttl_days=int(os.getenv("HH_SEEN_TTL_DAYS", "14")),
            resume_match=os.getenv("HH_RESUME_TITLE_MATCH", "Python разработчик").strip().lower(),
            fail_if_resume_not_found=os.getenv("HH_FAIL_IF_RESUME_NOT_FOUND", "true").lower() == "true",
            require_cover_letter=os.getenv("HH_REQUIRE_COVER_LETTER", "true").lower() == "true",
            max_pages=int(os.getenv("HH_MAX_PAGES", "100")),
            vacancies_csv=vacancies_csv,
            failed_vacancies_csv=failed_vacancies_csv,
            use_ai_cover_letter=os.getenv("HH_USE_AI_COVER_LETTER", "false").lower() == "true",
            openrouter_api_keys=openrouter_api_keys or [],
            ai_prompts_dir=Path(os.getenv("AI_PROMPTS_DIR", "data")),
            ai_model=os.getenv("AI_MODEL", "openai/gpt-oss-120b:free").strip(),
            use_hh_api_first=os.getenv("HH_USE_API_FIRST", "true").lower() == "true",
            hh_api_user_agent=os.getenv(
                "HH_API_USER_AGENT",
                "ZakirovCoverLetter/1.0 (zak.yuri@yandex.ru)",
            ).strip(),
            stop_words=stop_words or [],
        )
