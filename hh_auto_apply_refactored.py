"""
Refactored hh_auto_apply.py
- Читаемость, SOLID/DRY, тестируемость
- Исправлены баги со статистикой и истиной Enum
- Чистая архитектура: Config, DB, HHClient, Responder, App
- Аргументы CLI, dry-run, headless флаг
"""
from __future__ import annotations

import csv
import os
import sys
import re
import time
import random
import sqlite3
import signal
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict
from urllib.parse import urlencode


from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from playwright.sync_api import (
    sync_playwright, Page, BrowserContext, TimeoutError as PWTimeoutError
)
import argparse

# =========================
# Конфигурация
# =========================

@dataclass(frozen=True)
class Config:
    search_query: str = "python"
    region_ids: List[str] = None
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
        load_dotenv()
        region_ids = [r.strip() for r in os.getenv("HH_REGION_IDS", "").split(",") if r.strip()]
        # получить csv из окружения: сначала HH_VACANCIES_CSV, потом HH_COMPANIES_CSV (старое имя), иначе дефолт
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


# =========================
# Утилиты
# =========================

VAC_ID_RE = re.compile(r"/vacancy/(\d+)")


def human_pause(cfg: Config, a: float | None = None, b: float | None = None) -> None:
    a = cfg.min_sleep if a is None else a
    b = cfg.max_sleep if b is None else b
    time.sleep(random.uniform(a, b))


def extract_vacancy_id(url: str) -> str:
    m = VAC_ID_RE.search(url)
    return m.group(1) if m else url.split("/")[-1].split("?")[0]


# =========================
# БД (инфраструктура)
# =========================

class SeenRepo:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init(self):
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_vacancies (
                    id TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL
                )
                """
            )
            c.commit()

    def cleanup(self, ttl_days: int):
        if ttl_days <= 0:
            return
        cutoff = (datetime.utcnow() - timedelta(days=ttl_days)).isoformat()
        with self._conn() as c:
            c.execute("DELETE FROM seen_vacancies WHERE first_seen_at < ?", (cutoff,))
            c.commit()

    def is_seen(self, vac_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("SELECT 1 FROM seen_vacancies WHERE id = ?", (vac_id,))
            return cur.fetchone() is not None

    def mark_seen(self, vac_id: str) -> None:
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT OR IGNORE INTO seen_vacancies (id, first_seen_at) VALUES (?, ?)",
                    (vac_id, datetime.utcnow().isoformat()),
                )
                c.commit()
        except Exception:
            logger.debug("mark_seen failed; ignoring")


# =========================
# Домейн (модель)
# =========================

class ApplyResult(str, Enum):
    SUCCESS = "success"
    SKIPPED_ALREADY_APPLIED = "skipped_already_applied"
    ERROR = "error"


@dataclass
class Stats:
    found_links: int = 0
    skipped_seen: int = 0
    skipped_already: int = 0
    opened: int = 0
    applies_done: int = 0
    errors: int = 0

    def bump(self, key: str, inc: int = 1) -> None:
        setattr(self, key, getattr(self, key) + inc)


# =========================
# HH Client (Playwright обёртка)
# =========================

class HHClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        Path(cfg.screenshots_dir).mkdir(parents=True, exist_ok=True)

    # --------- Вспомогательные методы UI ---------
    @staticmethod
    def is_visible(locator, timeout: int = 1000) -> bool:
        try:
            locator.first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def make_shot(self, page: Page, tag: str) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"hh_{tag}_{ts}.png"
        path = str(Path(self.cfg.screenshots_dir) / fname)
        try:
            page.screenshot(path=path, full_page=True)
            logger.warning(f"Скриншот сохранён: {path}")
        except Exception as e:
            logger.warning(f"Не удалось сделать скриншот: {e}")

    # --------- Навигация ---------
    def build_search_url(self, page_num: int = 0) -> str:
        params: Dict[str, object] = {
            "text": self.cfg.search_query,
            "page": page_num,
            "search_field": ["name", "company_name", "description"],
            "order_by": "relevance",
        }
        if self.cfg.region_ids:
            params["area"] = self.cfg.region_ids
        if self.cfg.remote_only:
            params["schedule"] = "remote"
        return f"{self.cfg.base_url}/search/vacancy?{urlencode(params, doseq=True)}"

    def ensure_logged_in(self, page: Page) -> None:
        page.goto(self.cfg.base_url, wait_until="domcontentloaded")
        selectors = [
            '[data-qa="mainmenu_applicantProfile"]',
            'a[href*="/applicant/resumes"]',
            '[aria-label*="Профиль"]',
        ]
        for sel in selectors:
            if self.is_visible(page.locator(sel), timeout=1200):
                logger.info("Похоже, уже залогинены.")
                return

        logger.warning("Не обнаружен логин. Пожалуйста, войдите на hh.ru в открывшемся окне.")
        page.goto(self.cfg.base_url + "/account/login", wait_until="domcontentloaded")
        input("После входа нажмите Enter в консоли...")
        page.goto(self.cfg.base_url, wait_until="domcontentloaded")
        human_pause(self.cfg)
        logger.info("Продолжаем работу.")

    def list_vacancy_links_on_page(self, page: Page) -> List[str]:
        links: set[str] = set()
        selectors = [
            '[data-qa="vacancy-serp__vacancy-title"]',
            '[data-qa="serp-item__title"]',
            'a.bloko-link[data-qa*="title"]',
        ]
        for sel in selectors:
            cards = page.locator(sel)
            for i in range(cards.count()):
                href = cards.nth(i).get_attribute("href")
                if href and "/vacancy/" in href:
                    links.add(href.split("?")[0])

        if not links:
            wrappers = page.locator('[data-qa="vacancy-serp__vacancy"] , [data-qa="serp-item"]')
            for i in range(min(wrappers.count(), 60)):
                a = wrappers.nth(i).locator('a[href*="/vacancy/"]')
                if a.count():
                    href = a.first.get_attribute("href")
                    if href:
                        links.add(href.split("?")[0])

        if not links:
            logger.warning("Не нашли стандартные селекторы, пробуем запасной метод.")
            cards_alt = page.locator('a[href*="/vacancy/"]:visible')
            for i in range(min(cards_alt.count(), 80)):
                href = cards_alt.nth(i).get_attribute("href")
                if href:
                    links.add(href.split("?")[0])

        return list(links)

    def get_apply_button(self, page: Page):
        candidates = [
            page.get_by_role("button", name="Откликнуться"),
            page.get_by_role("link", name="Откликнуться"),
            page.locator('[data-qa="vacancy-response-link-top"]'),
            page.locator('[data-qa="vacancy-sidebar-submit"]'),
            page.locator('button:has-text("Откликнуться")'),
            page.locator('a:has-text("Откликнуться")'),
        ]
        for c in candidates:
            if self.is_visible(c, timeout=900):
                return c.first
        return None

    def already_applied(self, page: Page) -> bool:
        applied_text_variants = [
            "Отклик отправлен", "Вы откликнулись", "Отклик уже отправлен", "Отклик отправлен работодателю"
        ]
        for txt in applied_text_variants:
            if self.is_visible(page.get_by_text(txt, exact=False), timeout=500):
                return True
        return self.get_apply_button(page) is None

    def select_specific_resume(self, page: Page, mask: str) -> bool:
        containers = [
            '[data-qa="resume-select_item"]',
            '[data-qa="resume-select"] [data-qa="resume-item"]',
            '[data-qa*="resume"]',
            'label:has-text("-")',
        ]
        textual = [
            f'xpath=//div[contains(@data-qa,"resume")][.//text()[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮabcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю", "abcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю"), "{mask}")]]',
            f'xpath=//label[.//text()[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮabcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю", "abcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю"), "{mask}")]]',
            f'xpath=//a[contains(@href,"resume")][contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮabcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю", "abcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю"), "{mask}")]/ancestor::label|//a[contains(@href,"resume")][contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮabcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю", "abcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю"), "{mask}")]/ancestor::*[contains(@data-qa,"resume-select_item")]',
        ]
        for sel in textual:
            loc = page.locator(sel)
            if loc.count() > 0 and self.is_visible(loc, timeout=700):
                try:
                    radio = loc.locator('input[type="radio"]').first
                    if radio.count() > 0 and radio.is_visible():
                        radio.check()
                    else:
                        loc.first.click()
                    logger.info(f'Выбрано резюме по маске: "{mask}"')
                    return True
                except Exception:
                    continue
        for sel in containers:
            items = page.locator(sel)
            n = min(items.count(), 10)
            for i in range(n):
                item = items.nth(i)
                try:
                    if not self.is_visible(item, timeout=400):
                        continue
                    text = (item.inner_text() or "").strip().lower()
                    if mask in text:
                        radio = item.locator('input[type="radio"]').first
                        if radio.count() > 0 and radio.is_visible():
                            radio.check()
                        else:
                            item.click()
                        logger.info(f'Выбрано резюме по маске: "{mask}"')
                        return True
                except Exception:
                    continue
        logger.warning(f'Не найдено резюме с маской "{mask}".')
        return False

    def select_any_resume_if_needed(self, page: Page) -> bool:
        candidates = [
            '[data-qa="resume-select_item"]',
            'input[name="resume"]',
            'input[type="radio"][value*="resume"]',
        ]
        for sel in candidates:
            loc = page.locator(sel)
            if loc.count() > 0 and self.is_visible(loc, timeout=800):
                try:
                    el = loc.first
                    t = (el.get_attribute("type") or "").lower()
                    if t == "radio":
                        el.check()
                    else:
                        el.click()
                    logger.info("Выбрано первое доступное резюме (fallback).")
                    return True
                except Exception:
                    continue
        return False

    def check_consents_if_needed(self, page: Page) -> None:
        consent_candidates = [
            'input[type="checkbox"][name*="agreement"]',
            'input[type="checkbox"][data-qa*="consent"]',
            'input[type="checkbox"][required]',
        ]
        try:
            for sel in consent_candidates:
                boxes = page.locator(sel)
                count = min(boxes.count(), 6)
                for i in range(count):
                    box = boxes.nth(i)
                    try:
                        if self.is_visible(box, timeout=300) and not box.is_checked():
                            box.check()
                            logger.info("Поставлен чекбокс согласия.")
                    except Exception:
                        continue
        except Exception:
            pass

    def fill_cover_letter_with_verification(self, page: Page, cover_text: str) -> bool:
        try:
            togglers = [
                page.get_by_role("button", name="Добавить сопроводительное"),
                page.get_by_text("Добавить сопроводительное"),
                page.locator('[data-qa="vacancy-response-letter-toggle"]'),
            ]
            for t in togglers:
                if self.is_visible(t, timeout=800):
                    t.first.click()
                    human_pause(self.cfg, 0.3, 0.6)
                    break
        except Exception:
            pass

        textarea_selectors = [
            'textarea[data-qa="vacancy-response-letter-input"]',
            'textarea[placeholder*="сопроводительное"]',
            'textarea',
        ]
        for attempt in range(3):
            for sel in textarea_selectors:
                ta = page.locator(sel).first
                try:
                    if not self.is_visible(ta, timeout=900):
                        continue
                    ta.click()
                    page.keyboard.press("Control+A")
                    ta.fill(cover_text)
                    human_pause(self.cfg, 0.2, 0.4)
                    val = ta.input_value().strip()
                    if len(val) >= min(20, len(cover_text) // 2):
                        logger.info("Сопроводительное письмо заполнено и подтверждено.")
                        return True
                except Exception:
                    continue
            human_pause(self.cfg, 0.4, 0.8)
        logger.warning("Не удалось подтвердить наличие сопроводительного письма в форме.")
        return False

    # высокоуровневая отправка отклика на странице вакансии
    def add_cover_letter_and_submit(self, page: Page, cover_text: str) -> bool:
        letter_ok = self.fill_cover_letter_with_verification(page, cover_text)
        if app_cfg.require_cover_letter and not letter_ok:
            self.make_shot(page, "no_cover_letter")
            logger.warning("Отклик не отправляем: сопроводительное не удалось вставить (REQUIRE_COVER_LETTER=true).")
            return False

        selected_exact = self.select_specific_resume(page, app_cfg.resume_match)
        if not selected_exact:
            if app_cfg.fail_if_resume_not_found:
                self.make_shot(page, "resume_not_found")
                logger.warning("Отклик не отправляем: нужное резюме не найдено (FAIL_IF_RESUME_NOT_FOUND=true).")
                return False
            else:
                self.select_any_resume_if_needed(page)

        self.check_consents_if_needed(page)

        submit_candidates = [
            '[data-qa="vacancy-response-submit-button"]',
            'button:has-text("Отправить отклик")',
            'button:has-text("Отправить")',
            'button[data-qa*="submit"]',
        ]

        def find_enabled_submit():
            for sel in submit_candidates:
                btn = page.locator(sel).first
                try:
                    if self.is_visible(btn, timeout=900):
                        disabled = btn.get_attribute("disabled")
                        aria = btn.get_attribute("aria-disabled")
                        if not disabled and (aria is None or aria == "false"):
                            return btn
                except Exception:
                    continue
            return None

        for _ in range(3):
            btn = find_enabled_submit()
            if btn:
                try:
                    btn.scroll_into_view_if_needed()
                except Exception:
                    pass
                human_pause(self.cfg)
                try:
                    btn.click()
                    page.wait_for_timeout(1500)
                    if self.already_applied(page):
                        logger.success("Отклик отправлен ✅")
                        return True
                    page.wait_for_timeout(1500)
                    if self.already_applied(page):
                        logger.success("Отклик отправлен ✅")
                        return True
                except Exception as e:
                    logger.warning(f"Клик по кнопке отправки не удался: {e}")
            else:
                self.check_consents_if_needed(page)
                human_pause(self.cfg, 1, 2)
        logger.warning("Не удалось отправить отклик (возможно, капча или обязательные поля).")
        self.make_shot(page, "submit_fail")
        return False

    def apply_to_vacancy(self, context: BrowserContext, url: str, cover_text: str) -> tuple[ApplyResult, str]:
        logger.info(f"Открываю вакансию: {url}")
        page = context.new_page()
        page.on("console", lambda msg: logger.debug(f"[browser] {msg.type} {msg.text}"))
        title = ""
        try:
            page.set_default_timeout(30000)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            human_pause(self.cfg)

            # попытка считать заголовок вакансии — несколько селекторов в fallback'е
            title_selectors = [
                'h1',
                '[data-qa="vacancy-title"]',
                '[data-qa="vacancy-view-title"]',
                '.vacancy-title',
            ]
            for sel in title_selectors:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        t = (loc.first.inner_text() or "").strip()
                        if t:
                            title = t
                            break
                except Exception:
                    continue
            if not title:
                try:
                    title = (page.title() or "").strip()
                except Exception:
                    title = ""

            if self.already_applied(page):
                logger.info("Отклик уже был отправлен — пропускаю.")
                page.close()
                return ApplyResult.SKIPPED_ALREADY_APPLIED, title

            apply_btn = self.get_apply_button(page)
            if apply_btn:
                try:
                    apply_btn.click()
                except Exception:
                    pass
                page.wait_for_timeout(1000)

            ok = self.add_cover_letter_and_submit(page, cover_text)
            page.close()
            return (ApplyResult.SUCCESS, title) if ok else (ApplyResult.ERROR, title)

        except PWTimeoutError:
            logger.error("Таймаут при открытии вакансии.")
            try:
                self.make_shot(page, "vacancy_timeout")
            except Exception:
                pass
            try:
                page.close()
            except Exception:
                pass
            return ApplyResult.ERROR, title
        except Exception as e:
            logger.exception(f"Ошибка при обработке вакансии: {e}")
            try:
                slug = url.split("/")[-1][:30]
                self.make_shot(page, f"error_{slug}")
            except Exception:
                pass
            try:
                page.close()
            except Exception:
                pass
            return ApplyResult.ERROR, title


# =========================
# Приложение (оркестрация)
# =========================

class App:
    def __init__(self, cfg: Config, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.repo = SeenRepo(cfg.db_path)
        self.client = HHClient(cfg)
        self._stop = False

    def _ensure_csv(self) -> None:
        p = Path(self.cfg.vacancies_csv)
        if not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            # создать файл и записать хедер
            with p.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["title", "link"])

    def _append_vacancy_to_csv(self, title: str, link: str) -> None:
        p = Path(self.cfg.vacancies_csv)
        # если файла нет — создать с хедером
        if not p.exists():
            self._ensure_csv()
        # записать строку
        with p.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([title, link])

    def _read_cover_letter(self) -> str:
        p = self.cfg.cover_letter_path
        if not p.exists():
            logger.error("Не найден cover_letter.txt рядом со скриптом.")
            sys.exit(1)
        txt = p.read_text(encoding="utf-8").strip()
        if not txt:
            logger.error("Файл cover_letter.txt пуст.")
            sys.exit(1)
        return txt

    def stop(self, *_):
        self._stop = True
        logger.warning("Получен сигнал прерывания. Завершаем после текущего действия…")

    def run(self) -> int:
        logger.remove()
        logger.add(sys.stdout, level="DEBUG" if self.cfg.verbose else "INFO", colorize=True, format="<level>{message}</level>")

        # Гигиена
        self.repo.cleanup(self.cfg.seen_ttl_days)
        Path(self.cfg.screenshots_dir).mkdir(parents=True, exist_ok=True)

        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        stats = Stats()
        cover_text = self._read_cover_letter()
        self._ensure_csv()

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.cfg.persist_dir,
                headless=self.cfg.headless,
                args=["--start-maximized"],
                viewport={"width": 1366, "height": 900},
                slow_mo=self.cfg.slow_mo_ms,
            )
            page = context.new_page()
            page.set_default_timeout(30000)
            page.on("console", lambda msg: logger.debug(f"[browser] {msg.type} {msg.text}"))

            self.client.ensure_logged_in(page)

            applies_done = 0
            page_num = 0
            empty_pages = 0

            while not self._stop and applies_done < self.cfg.max_applies and page_num < self.cfg.max_pages:
                search_url = self.client.build_search_url(page_num)
                logger.info(f"Страница поиска: {search_url}")
                page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                human_pause(self.cfg)

                links = self.client.list_vacancy_links_on_page(page)
                if not links:
                    empty_pages += 1
                    if empty_pages >= self.cfg.empty_pages_tolerance:
                        logger.info("Несколько пустых страниц подряд — завершаю.")
                        break
                    page_num += 1
                    continue

                empty_pages = 0
                logger.info(f"Найдено вакансий на странице: {len(links)}")
                stats.bump("found_links", len(links))

                for vurl in links:
                    if self._stop:
                        break
                    if applies_done >= self.cfg.max_applies:
                        break

                    vac_id = extract_vacancy_id(vurl)
                    if self.repo.is_seen(vac_id):
                        stats.bump("skipped_seen")
                        logger.info("Эта вакансия уже посещалась ранее — пропускаю.")
                        continue

                    stats.bump("opened")

                    if self.dry_run:
                        logger.info(f"[DRY-RUN] Отклик не отправляется. URL: {vurl}")
                        result, title = ApplyResult.SUCCESS, "(dry-run)"
                    else:
                        result, title = self.client.apply_to_vacancy(context, vurl, cover_text)

                    self.repo.mark_seen(vac_id)

                    if result is ApplyResult.SUCCESS:
                        applies_done += 1
                        stats.bump("applies_done")
                        # записать в CSV
                        try:
                            # если title пустой — используем ссылку как заголовок-фоллбек
                            self._append_vacancy_to_csv(title if title else vurl, vurl)
                            logger.info(f"Сохранено в CSV: {title} — {vurl}")
                        except Exception as e:
                            logger.warning(f"Не удалось сохранить в CSV: {e}")
                    elif result is ApplyResult.SKIPPED_ALREADY_APPLIED:
                        stats.bump("skipped_already")
                    else:
                        stats.bump("errors")

                    human_pause(self.cfg)

                page_num += 1

            logger.info("========== ОТЧЁТ ==========")
            logger.info(f"Всего ссылок найдено:    {stats.found_links}")
            logger.info(f"Пропущено (ранее были):  {stats.skipped_seen}")
            logger.info(f"Пропущено (уже отклик):  {stats.skipped_already}")
            logger.info(f"Открыто/обработано:      {stats.opened}")
            logger.info(f"Успешных откликов:       {stats.applies_done}")
            logger.info(f"Ошибок/неуспехов:        {stats.errors}")
            logger.info(f"Лимит откликов (MAX):    {self.cfg.max_applies}")
            logger.info("========== /ОТЧЁТ ==========")

            context.close()
        return 0


# =========================
# CLI
# =========================

def build_cli_cfg() -> tuple[Config, bool]:
    parser = argparse.ArgumentParser(description="Auto-apply to vacancies on hh.ru")
    parser.add_argument("--headless", action="store_true", help="Запуск браузера без UI")
    parser.add_argument("--dry-run", action="store_true", help="Не отправлять отклики, только сканировать")
    parser.add_argument("--verbose", action="store_true", help="Подробные логи")
    parser.add_argument("--query", type=str, help="Переопределить запрос поиска")
    args = parser.parse_args()

    cfg = Config.from_env()
    # переопределения из CLI
    object.__setattr__(cfg, "headless", bool(args.headless))
    object.__setattr__(cfg, "verbose", bool(args.verbose))
    if args.query:
        object.__setattr__(cfg, "search_query", args.query.strip())
    return cfg, bool(args.dry_run)


if __name__ == "__main__":
    app_cfg, dry = build_cli_cfg()
    app = App(app_cfg, dry_run=dry)
    sys.exit(app.run())
