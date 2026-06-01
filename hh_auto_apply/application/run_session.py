import csv
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from loguru import logger
from playwright.sync_api import sync_playwright

from hh_auto_apply.core.config import Config
from hh_auto_apply.domain.entities import ApplyResult, Stats
from hh_auto_apply.infrastructure.browser.factory import make_client
from hh_auto_apply.infrastructure.persistence.seen_repo import SeenRepo
from hh_auto_apply.infrastructure.utils import human_pause


class App:
    def __init__(self, cfg: Config, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.repo = SeenRepo(cfg.db_path)
        self.client = make_client(cfg)
        self._stop = False

        # Отдельные CSV-файлы под каждую площадку (кроме hh — он остаётся как был,
        # для обратной совместимости). Для LinkedIn получится, например:
        #   data/vacancies_linkedin.csv и data/vacancies_failed_linkedin.csv
        self.vacancies_csv = self._platform_csv_path(cfg.vacancies_csv)
        self.failed_vacancies_csv = self._platform_csv_path(cfg.failed_vacancies_csv)

    def _platform_csv_path(self, path_str: str) -> str:
        """Добавляет суффикс площадки к имени CSV для всех площадок, кроме hh."""
        platform = self.client.platform
        if platform == "hh":
            return path_str
        p = Path(path_str)
        return str(p.with_name(f"{p.stem}_{platform}{p.suffix}"))

    def _add_date_header_if_needed(self, filepath: Path, date_str: str) -> None:
        """Добавляет строку с датой если её ещё нет или дата изменилась."""
        try:
            content = filepath.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            
            # Проверяем, есть ли уже такая дата в конце файла
            if lines and lines[-1] == f"# {date_str}":
                return
            
            # Если файл содержит какие-то данные и последняя строка не дата, добавляем
            if lines and not lines[-1].startswith("#"):
                filepath.write_text(content + f"\n# {date_str}\n", encoding="utf-8")
            elif not lines or (lines and lines[-1].startswith("#")):
                # Если последняя строка - дата, просто добавляем новую
                if lines and lines[-1].startswith("#") and lines[-1] != f"# {date_str}":
                    filepath.write_text(content + f"\n# {date_str}\n", encoding="utf-8")
        except Exception as e:
            logger.debug(f"Ошибка при добавлении даты в CSV: {e}")

    def _ensure_csv(self) -> None:
        p = Path(self.vacancies_csv)
        if not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            with p.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["title", "link"])

    def _append_vacancy_to_csv(self, title: str, link: str) -> None:
        p = Path(self.vacancies_csv)
        if not p.exists():
            self._ensure_csv()
        
        # Проверяем, нужно ли добавить дату
        current_date = datetime.now().strftime("%d.%m.%Y")
        self._add_date_header_if_needed(p, current_date)
        
        with p.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([title, link])

    def _ensure_failed_csv(self) -> None:
        """Создаёт файл с ошибочными вакансиями если его нет."""
        p = Path(self.failed_vacancies_csv)
        if not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            with p.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["title", "link", "error_type"])

    def _append_failed_vacancy_to_csv(self, title: str, link: str, error_type: str) -> None:
        """Добавляет вакансию в файл ошибок.
        
        Args:
            title: Название вакансии
            link: Ссылка на вакансию
        
        # Проверяем, нужно ли добавить дату
        current_date = datetime.now().strftime("%d.%m.%Y")
        self._add_date_header_if_needed(p, current_date)
        
            error_type: Тип ошибки (ERROR, TIMEOUT, RESUME_NOT_FOUND, NO_COVER_LETTER)
        """
        p = Path(self.failed_vacancies_csv)
        if not p.exists():
            self._ensure_failed_csv()
        with p.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([title, link, error_type])

    def _read_cover_letter(self) -> str:
        p = self.cfg.cover_letter_path
        # Для LinkedIn сопроводительное письмо необязательно: в Easy Apply
        # поле письма присутствует не всегда. Не валимся, если файла нет.
        linkedin = self.cfg.platform.strip().lower() in ("linkedin", "li")
        if not p.exists():
            if linkedin:
                logger.warning("cover_letter.txt не найден — продолжаю без письма (LinkedIn).")
                return ""
            logger.error("Не найден cover_letter.txt рядом со скриптом.")
            sys.exit(1)
        txt = p.read_text(encoding="utf-8").strip()
        if not txt:
            if linkedin:
                logger.warning("cover_letter.txt пуст — продолжаю без письма (LinkedIn).")
                return ""
            logger.error("Файл cover_letter.txt пуст.")
            sys.exit(1)
        return txt

    def stop(self, *_):
        self._stop = True
        logger.warning("Получен сигнал прерывания. Завершаем после текущего действия…")

    def _matches_stop_word(self, title: str) -> str | None:
        """Проверяет, содержит ли название вакансии стоп-слово.

        Сравнение идёт без учёта регистра, с границами слов
        (чтобы "QA" не сматчил "Equanimity", а "Java" не сматчил "JavaScript").

        Returns:
            Найденное стоп-слово или None, если ничего не найдено.
        """
        if not title or not self.cfg.stop_words:
            return None
        title_lower = title.lower()
        for word in self.cfg.stop_words:
            word_lower = word.strip().lower()
            if not word_lower:
                continue
            # Граница слова: символ не должен быть буквой/цифрой
            pattern = r"(?<!\w)" + re.escape(word_lower) + r"(?!\w)"
            if re.search(pattern, title_lower):
                return word
        return None

    def run(self) -> int:
        logger.remove()
        logger.add(sys.stdout, level="DEBUG" if self.cfg.verbose else "INFO", colorize=True, format="<level>{message}</level>")
        logger.info(f"Запуск с конфигом: search_query={self.cfg.search_query!r} | resume_match={self.cfg.resume_match!r}")

        self.repo.cleanup(self.cfg.seen_ttl_days)
        Path(self.cfg.screenshots_dir).mkdir(parents=True, exist_ok=True)

        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        stats = Stats()
        cover_text = self._read_cover_letter()
        self._ensure_csv()
        self._ensure_failed_csv()
        start_time = time.time()

        try:
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

                    vacancies = self.client.list_vacancies_with_titles(page)
                    if not vacancies:
                        empty_pages += 1
                        if empty_pages >= self.cfg.empty_pages_tolerance:
                            logger.info("Несколько пустых страниц подряд — завершаю.")
                            break
                        page_num += 1
                        continue

                    empty_pages = 0
                    logger.info(f"Найдено вакансий на странице: {len(vacancies)}")
                    stats.bump("found_links", len(vacancies))

                    if self.cfg.stop_words:
                        logger.debug(f"Стоп-слова активны: {len(self.cfg.stop_words)} шт.")

                    for vurl, vtitle in vacancies:
                        if self._stop:
                            break
                        if applies_done >= self.cfg.max_applies:
                            break

                        vac_id = f"{self.client.platform}:{self.client.extract_job_id(vurl)}"
                        if self.repo.is_seen(vac_id):
                            stats.bump("skipped_seen")
                            logger.info("Эта вакансия уже посещалась ранее — пропускаю.")
                            continue

                        # Фильтр по стоп-словам в названии вакансии
                        matched_stop = self._matches_stop_word(vtitle)
                        if matched_stop:
                            stats.bump("skipped_stop_word")
                            logger.info(
                                f"Пропускаю по стоп-слову '{matched_stop}': {vtitle}"
                            )
                            # Отмечаем как seen, чтобы повторно не натыкаться
                            self.repo.mark_seen(vac_id)
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
                        elif result in (
                            ApplyResult.SKIPPED_EXTERNAL,
                            ApplyResult.SKIPPED_FORM_INCOMPLETE,
                        ):
                            # Это не сбой бота, а вакансии, на которые отклик через
                            # Easy Apply невозможен. Пишем в failed-файл с понятной
                            # причиной, но не считаем ошибками.
                            if result is ApplyResult.SKIPPED_EXTERNAL:
                                stats.bump("skipped_external")
                            else:
                                stats.bump("skipped_form")
                            try:
                                self._append_failed_vacancy_to_csv(
                                    title if title else vurl, vurl, result.value
                                )
                            except Exception as e:
                                logger.warning(f"Не удалось сохранить причину в CSV: {e}")
                        else:
                            stats.bump("errors")
                            # Сохраняем ошибочные вакансии в отдельный файл
                            try:
                                error_type = result.value if hasattr(result, 'value') else str(result)
                                self._append_failed_vacancy_to_csv(title if title else vurl, vurl, error_type)
                                logger.info(f"Ошибка сохранена в {self.failed_vacancies_csv}: {title} — {vurl}")
                            except Exception as e:
                                logger.warning(f"Не удалось сохранить ошибку в CSV: {e}")

                        human_pause(self.cfg)

                    page_num += 1
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
        finally:
            end_time = time.time()
            elapsed = end_time - start_time
            success_rate = (stats.applies_done / stats.opened * 100) if stats.opened > 0 else 0

            logger.info("========== ОТЧЁТ ==========")
            logger.info(f"Всего ссылок найдено:        {stats.found_links}")
            logger.info(f"Пропущено (ранее были):      {stats.skipped_seen}")
            logger.info(f"Пропущено (стоп-слово):      {stats.skipped_stop_word}")
            logger.info(f"Пропущено (уже отклик):      {stats.skipped_already}")
            logger.info(f"Пропущено (внешняя форма):   {stats.skipped_external}")
            logger.info(f"Пропущено (форма с вопросами):{stats.skipped_form}")
            logger.info(f"Открыто/обработано:          {stats.opened}")
            logger.info(f"Успешных откликов:           {stats.applies_done}")
            logger.info(f"Ошибок (сбои бота):          {stats.errors}")
            logger.info(f"Процент успешности:          {success_rate:.1f}%")
            logger.info(f"Лимит откликов (MAX):        {self.cfg.max_applies}")
            logger.info(f"Время работы:                {elapsed:.2f} сек")
            logger.info("========== /ОТЧЁТ ==========")
        return 0
