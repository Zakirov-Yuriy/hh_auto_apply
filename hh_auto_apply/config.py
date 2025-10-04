from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class Config:
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
    cover_letter_path: Path = Path("cover_letter.txt")
    base_url: str = "https://hh.ru"
    max_pages: int = 100
    empty_pages_tolerance: int = 3
    headless: bool = False
    slow_mo_ms: int = 50
    verbose: bool = False
    vacancies_csv: str = "vacancies.csv"

    @staticmethod
    def from_env() -> "Config":
        from dotenv import load_dotenv
        load_dotenv()
        
        region_ids = [r.strip() for r in os.getenv("HH_REGION_IDS", "").split(",") if r.strip()]
        vacancies_csv = os.getenv("HH_VACANCIES_CSV") or os.getenv("HH_COMPANIES_CSV") or "vacancies.csv"
        
        return Config(
            search_query=os.getenv("HH_SEARCH_QUERY", "python").strip(),
            region_ids=region_ids or [],
            remote_only=os.getenv("HH_REMOTE_ONLY", "false").lower() == "true",
            max_applies=int(os.getenv("HH_MAX_APPLIES", "200")),
            min_sleep=float(os.getenv("HH_MIN_SLEEP", "3")),
            max_sleep=float(os.getenv("HH_MAX_SLEEP", "7")),
            persist_dir=os.getenv("HH_PERSIST_DIR", ".hh_user"),
            screenshots_dir=os.getenv("HH_SCREENSHOTS_DIR", "screenshots"),
            db_path=os.getenv("HH_DB_PATH", "hh_seen.sqlite"),
            seen_ttl_days=int(os.getenv("HH_SEEN_TTL_DAYS", "14")),
            resume_match=os.getenv("HH_RESUME_TITLE_MATCH", "Python разработчик").strip().lower(),
            fail_if_resume_not_found=os.getenv("HH_FAIL_IF_RESUME_NOT_FOUND", "true").lower() == "true",
            require_cover_letter=os.getenv("HH_REQUIRE_COVER_LETTER", "true").lower() == "true",
            max_pages=int(os.getenv("HH_MAX_PAGES", "100")),
            vacancies_csv=vacancies_csv,
        )

def build_cli_cfg() -> tuple[Config, bool]:
    parser = argparse.ArgumentParser(description="Auto-apply to vacancies on hh.ru")
    parser.add_argument("--headless", action="store_true", help="Запуск браузера без UI")
    parser.add_argument("--dry-run", action="store_true", help="Не отправлять отклики, только сканировать")
    parser.add_argument("--verbose", action="store_true", help="Подробные логи")
    parser.add_argument("--query", type=str, help="Переопределить запрос поиска")
    args = parser.parse_args()

    cfg = Config.from_env()
    
    # Создаем новый экземпляр с изменениями из CLI вместо setattr
    updates = {
        "headless": bool(args.headless),
        "verbose": bool(args.verbose),
    }
    if args.query:
        updates["search_query"] = args.query.strip()
        
    cfg = replace(cfg, **updates)
    
    return cfg, bool(args.dry_run)
