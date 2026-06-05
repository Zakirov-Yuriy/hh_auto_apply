"""Core configuration module for hh_auto_apply application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


# Сопоставление названий уровней опыта (рус/англ) кодам LinkedIn (f_E).
_LINKEDIN_EXPERIENCE_MAP = {
    "1": "1", "стажер": "1", "стажёр": "1", "intern": "1",
    "internship": "1", "trainee": "1",
    "2": "2", "молодой специалист": "2", "entry": "2",
    "entry level": "2", "junior": "2", "начинающий": "2",
    "3": "3", "специалист": "3", "associate": "3", "mid": "3",
    "4": "4", "старший": "4", "senior": "4", "mid-senior": "4",
    "5": "5", "директор": "5", "director": "5", "руководитель": "5",
    "6": "6", "executive": "6", "высшее руководство": "6",
}


def parse_experience_levels(raw: str) -> List[str]:
    """Парсит строку уровней опыта в коды LinkedIn f_E, сохраняя порядок без дублей.

    Принимает и коды ("1,2,3"), и названия ("стажер, молодой специалист, специалист").
    Нераспознанные значения игнорируются.
    """
    codes: list[str] = []
    for part in (raw or "").split(","):
        key = part.strip().lower()
        if not key:
            continue
        code = _LINKEDIN_EXPERIENCE_MAP.get(key)
        if code and code not in codes:
            codes.append(code)
    return codes


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    # Площадка поиска работы: "hh" или "linkedin".
    platform: str = "hh"
    # Текстовая локация для LinkedIn (region_ids от hh там не работают).
    # Например: "Russia", "Remote", "Germany". Пусто = без фильтра по локации
    # (поиск по всем странам).
    linkedin_location: str = ""
    # Уровни опыта LinkedIn (параметр f_E). Список кодов LinkedIn:
    # 1=Стажёр, 2=Молодой специалист, 3=Специалист,
    # 4=Старший/Mid-Senior, 5=Директор, 6=Высшее руководство.
    # По умолчанию: стажёр + молодой специалист + специалист.
    linkedin_experience_levels: List[str] | None = None

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
    # LinkedIn Easy Apply: тексты для полей Headline и Summary (необязательны).
    # Если файла нет или он пуст — соответствующее поле бот просто не трогает.
    linkedin_headline_path: Path = Path("data/linkedin_headline.txt")
    linkedin_summary_path: Path = Path("data/linkedin_summary.txt")
    # Город для поля "Location (city)" в форме Easy Apply (typeahead с подсказками).
    # Бот печатает это значение и выбирает первый вариант из выпадающего списка.
    # Пусто = поле не трогаем. Пример: "Manavgat".
    linkedin_city: str = ""
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

        # Уровни опыта LinkedIn: по умолчанию стажёр + молодой специалист + специалист.
        experience_levels = parse_experience_levels(
            os.getenv("LINKEDIN_EXPERIENCE_LEVELS", "1,2,3")
        )

        # У каждой площадки своя папка сессии браузера (разные cookies/логин),
        # если пользователь явно не задал HH_PERSIST_DIR.
        default_persist = ".linkedin_user" if platform in ("linkedin", "li") else ".hh_user"
        persist_dir = os.getenv("HH_PERSIST_DIR", default_persist)

        return Config(
            platform=platform,
            linkedin_location=os.getenv("LINKEDIN_LOCATION", "").strip(),
            linkedin_experience_levels=experience_levels or [],
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
            linkedin_headline_path=Path(
                os.getenv("LINKEDIN_HEADLINE_PATH", "data/linkedin_headline.txt")
            ),
            linkedin_summary_path=Path(
                os.getenv("LINKEDIN_SUMMARY_PATH", "data/linkedin_summary.txt")
            ),
            linkedin_city=os.getenv("LINKEDIN_CITY", "").strip(),
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
