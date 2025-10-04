import csv
import signal
import sys
from pathlib import Path

from loguru import logger
from playwright.sync_api import sync_playwright

from hh_auto_apply.client import HHClient
from hh_auto_apply.config import Config
from hh_auto_apply.domain import ApplyResult, Stats
from hh_auto_apply.persistence import SeenRepo
from hh_auto_apply.utils import extract_vacancy_id, human_pause


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
            with p.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["title", "link"])

    def _append_vacancy_to_csv(self, title: str, link: str) -> None:
        p = Path(self.cfg.vacancies_csv)
        if not p.exists():
            self._ensure_csv()
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
                        try:
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
