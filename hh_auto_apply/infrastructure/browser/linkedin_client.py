"""Клиент для LinkedIn Jobs: поиск вакансий и отклик через Easy Apply.

Реализует тот же интерфейс JobBoardClient, что и HHClient, поэтому
основной цикл приложения работает с ним без изменений.

ВНИМАНИЕ: LinkedIn активно противодействует автоматизации. Используйте
человекоподобные паузы (они уже встроены), консервативные лимиты откликов
и не запускайте бота слишком часто, чтобы снизить риск ограничений аккаунта.
Автоматизируется только Easy Apply (отклик внутри LinkedIn); вакансии с
внешней формой бот пропускает.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlencode

from loguru import logger
from playwright._impl._errors import TargetClosedError
from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeoutError

from hh_auto_apply.core.config import Config
from hh_auto_apply.domain.entities import ApplyResult
from hh_auto_apply.infrastructure.browser.linkedin_selectors import LinkedInSelectors as S
from hh_auto_apply.infrastructure.utils import human_pause

JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")
CURRENT_JOB_ID_RE = re.compile(r"currentJobId=(\d+)")

# Сколько шагов мастера Easy Apply максимально проходим, прежде чем сдаться.
MAX_EASY_APPLY_STEPS = 8


class LinkedInClient:
    """Площадка LinkedIn Jobs (поиск + Easy Apply)."""

    platform = "linkedin"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        Path(cfg.screenshots_dir).mkdir(parents=True, exist_ok=True)

    # --------- Вспомогательное ---------
    @staticmethod
    def is_visible(locator, timeout: int = 1000) -> bool:
        try:
            locator.first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def make_shot(self, page: Page, tag: str) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path(self.cfg.screenshots_dir) / "linkedin"
        path.mkdir(parents=True, exist_ok=True)
        fname = str(path / f"li_{tag}_{ts}.png")
        try:
            page.screenshot(path=fname, full_page=True)
            logger.warning(f"Скриншот сохранён: {fname}")
        except Exception as e:
            logger.warning(f"Не удалось сделать скриншот: {e}")

    def extract_job_id(self, url: str) -> str:
        m = JOB_ID_RE.search(url) or CURRENT_JOB_ID_RE.search(url)
        if m:
            return m.group(1)
        return url.split("?")[0].rstrip("/").split("/")[-1]

    # --------- Навигация ---------
    def build_search_url(self, page_num: int = 0) -> str:
        # LinkedIn пагинация: параметр start кратен 25.
        params: dict[str, object] = {
            "keywords": self.cfg.search_query,
            "start": page_num * 25,
            "f_AL": "true",  # только Easy Apply
        }
        if self.cfg.linkedin_location:
            params["location"] = self.cfg.linkedin_location
        if self.cfg.remote_only:
            params["f_WT"] = "2"  # тип работы: удалённо
        return f"https://www.linkedin.com/jobs/search/?{urlencode(params)}"

    def _is_logged_in(self, page: Page) -> bool:
        """Надёжная проверка входа по cookie li_at (не зависит от вёрстки).

        У авторизованной сессии LinkedIn всегда присутствует cookie ``li_at``.
        """
        try:
            cookies = page.context.cookies("https://www.linkedin.com")
            return any(c.get("name") == "li_at" and c.get("value") for c in cookies)
        except Exception:
            return False

    def ensure_logged_in(self, page: Page) -> None:
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        human_pause(self.cfg, 1.0, 2.0)

        if self._is_logged_in(page):
            logger.info("LinkedIn: вход подтверждён (активная сессия).")
            return

        # Не залогинены: гостю LinkedIn не показывает Easy Apply, поэтому
        # обязательно просим войти вручную и ждём подтверждения.
        logger.warning(
            "LinkedIn: вход не обнаружен. В открывшемся окне войдите в аккаунт "
            "(включая 2FA, если есть), дождитесь загрузки ленты."
        )
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        input("После входа в LinkedIn нажмите Enter в консоли...")

        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        human_pause(self.cfg)
        if self._is_logged_in(page):
            logger.info("LinkedIn: вход подтверждён.")
        else:
            logger.error(
                "LinkedIn: вход всё ещё не подтверждён (нет cookie li_at). "
                "Без входа Easy Apply недоступен. Проверьте, что вы вошли в том же окне."
            )

    def _scroll_results(self, page: Page) -> None:
        """Прокручивает левую панель результатов, чтобы подгрузить все карточки.

        LinkedIn подгружает вакансии лениво по мере прокрутки.
        """
        try:
            for _ in range(6):
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(700)
        except Exception as e:
            logger.debug(f"Прокрутка списка не удалась: {e}")

    def list_vacancies_with_titles(self, page: Page) -> List[Tuple[str, str]]:
        self._scroll_results(page)
        results: list[tuple[str, str]] = []
        seen: set[str] = set()

        try:
            links = page.locator(S.JOB_LINK_GENERIC)
            count = links.count()
        except Exception:
            # Страница/браузер могли быть закрыты (например, по Ctrl+C) — не падаем.
            return results
        for i in range(count):
            a = links.nth(i)
            try:
                href = a.get_attribute("href") or ""
            except Exception:
                continue
            if "/jobs/view/" not in href:
                continue
            # Нормализуем до абсолютного URL вида /jobs/view/<id>/
            job_id = self.extract_job_id(href)
            if not job_id.isdigit():
                continue
            clean_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
            if clean_url in seen:
                continue
            seen.add(clean_url)
            try:
                title = (a.get_attribute("aria-label") or a.inner_text() or "").strip()
            except Exception:
                title = ""
            # aria-label иногда содержит лишний текст вида "... with verification"
            title = title.split("\n")[0].strip()
            results.append((clean_url, title))

        logger.debug(f"LinkedIn: собрано вакансий на странице: {len(results)}")
        return results

    # --------- Отклик ---------
    def already_applied(self, page: Page) -> bool:
        try:
            body = (page.locator("body").inner_text() or "")
        except Exception:
            return False
        return any(marker in body for marker in S.ALREADY_APPLIED_TEXT)

    def _fill_cover_letter_if_present(self, page: Page, cover_text: str) -> None:
        if not cover_text:
            return
        ta = page.locator(S.COVER_LETTER_TEXTAREA)
        if ta.count() and self.is_visible(ta, timeout=800):
            try:
                if not (ta.first.input_value() or "").strip():
                    ta.first.fill(cover_text)
                    logger.info("LinkedIn: вставлено сопроводительное письмо.")
            except Exception as e:
                logger.debug(f"Не удалось заполнить сопроводительное: {e}")

    def _uncheck_follow_company(self, page: Page) -> None:
        cb = page.locator(S.FOLLOW_COMPANY_CHECKBOX)
        try:
            if cb.count() and cb.first.is_checked():
                cb.first.uncheck()
        except Exception:
            pass

    def _discard_application(self, page: Page) -> None:
        """Закрывает модальное окно Easy Apply и подтверждает выход без отправки."""
        try:
            dismiss = page.locator(S.DISMISS_BUTTON)
            if dismiss.count():
                dismiss.first.click()
                page.wait_for_timeout(600)
            discard = page.locator(S.DISCARD_BUTTON)
            if discard.count() and self.is_visible(discard, timeout=1200):
                discard.first.click()
                page.wait_for_timeout(400)
        except Exception as e:
            logger.debug(f"Не удалось аккуратно закрыть форму: {e}")

    def _run_easy_apply_modal(self, page: Page, cover_text: str) -> Tuple[bool, str]:
        """Проходит пошаговый мастер Easy Apply до кнопки Submit.

        Возвращает кортеж (успех, причина):
          (True, "")                 — отклик отправлен;
          (False, "form_incomplete") — форма требует данных, которые бот не заполняет;
          (False, "submit_failed")   — не удалось нажать Submit (техническая ошибка).
        """
        # Ждём появления любой кнопки формы (контактные данные / Далее / Отправить).
        any_button = f"{S.SUBMIT_BUTTON}, {S.NEXT_BUTTON}, {S.REVIEW_BUTTON}"
        try:
            page.wait_for_selector(any_button, timeout=8000)
        except Exception:
            logger.warning(
                "LinkedIn: форма Easy Apply не открылась (нет кнопок) — пропускаю вакансию."
            )
            self._discard_application(page)
            return False, "form_incomplete"

        for step in range(MAX_EASY_APPLY_STEPS):
            page.wait_for_timeout(900)
            self._fill_cover_letter_if_present(page, cover_text)
            self._uncheck_follow_company(page)

            submit = page.locator(S.SUBMIT_BUTTON)
            if submit.count() and self.is_visible(submit, timeout=600):
                try:
                    submit.first.click()
                    page.wait_for_timeout(1500)
                    logger.info("LinkedIn: отклик отправлен (Submit).")
                    dismiss = page.locator(S.DISMISS_BUTTON)
                    if dismiss.count():
                        try:
                            dismiss.first.click()
                        except Exception:
                            pass
                    return True, ""
                except Exception as e:
                    logger.warning(f"Не удалось нажать Submit: {e}")
                    self._discard_application(page)
                    return False, "submit_failed"

            review = page.locator(S.REVIEW_BUTTON)
            if review.count() and self.is_visible(review, timeout=600):
                try:
                    review.first.click()
                    continue
                except Exception:
                    pass

            nxt = page.locator(S.NEXT_BUTTON)
            if nxt.count() and self.is_visible(nxt, timeout=600):
                try:
                    nxt.first.click()
                    page.wait_for_timeout(900)
                    continue
                except Exception as e:
                    logger.debug(f"Не удалось нажать Next: {e}")
                    break

            # Нет ни Submit, ни Review, ни Next — продвинуться нельзя.
            logger.warning(
                "LinkedIn: форма Easy Apply требует данных, которые бот не заполняет. "
                "Пропускаю вакансию."
            )
            break

        self._discard_application(page)
        return False, "form_incomplete"

    def apply_to_vacancy(
        self, context: BrowserContext, url: str, cover_text: str
    ) -> Tuple[ApplyResult, str]:
        logger.info(f"LinkedIn: открываю вакансию: {url}")
        page = None
        title = ""
        try:
            page = context.new_page()
            page.set_default_timeout(30000)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            human_pause(self.cfg)

            # Название вакансии
            try:
                loc = page.locator(S.VACANCY_TITLE)
                if loc.count():
                    title = (loc.first.inner_text() or "").strip()
            except Exception:
                title = ""
            if not title:
                try:
                    title = (page.title() or "").strip()
                except Exception:
                    title = ""

            if self.already_applied(page):
                logger.info("LinkedIn: отклик уже был отправлен — пропускаю.")
                return ApplyResult.SKIPPED_ALREADY_APPLIED, title

            # Ищем триггер Easy Apply: ссылку "/apply/" (новый SDUI) или кнопку
            # с подписью "Простая подача заявки" / "Easy Apply".
            try:
                page.wait_for_selector(S.EASY_APPLY_TRIGGER, timeout=9000)
            except PWTimeoutError:
                logger.info(
                    "LinkedIn: Easy Apply на вакансии не найден (внешняя форма) — пропускаю."
                )
                return ApplyResult.SKIPPED_EXTERNAL, title

            trigger = page.locator(S.EASY_APPLY_TRIGGER).first
            if not self.is_visible(trigger, timeout=2000):
                logger.info("LinkedIn: кнопка Easy Apply не видна (внешняя форма) — пропускаю.")
                return ApplyResult.SKIPPED_EXTERNAL, title

            # Проверяем, что это именно Easy Apply, а не внешний отклик.
            try:
                aria = (trigger.get_attribute("aria-label") or "")
                txt = (trigger.inner_text() or "")
                href = (trigger.get_attribute("href") or "")
            except Exception:
                aria = txt = href = ""
            label = f"{aria} {txt}".lower()
            is_easy = (
                "простая подача" in label
                or "easy apply" in label
                or "/apply/" in href
            )
            if not is_easy:
                logger.info(
                    "LinkedIn: это не Easy Apply (внешняя форма на сайте компании) — пропускаю."
                )
                return ApplyResult.SKIPPED_EXTERNAL, title

            try:
                trigger.click()
            except Exception as e:
                logger.warning(f"Не удалось нажать Easy Apply: {e}")
                return ApplyResult.ERROR, title

            # Новый флоу может открыть отдельную страницу /apply/, классический — модалку.
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(1500)

            ok, reason = self._run_easy_apply_modal(page, cover_text)
            if ok:
                return ApplyResult.SUCCESS, title
            if reason == "form_incomplete":
                return ApplyResult.SKIPPED_FORM_INCOMPLETE, title
            return ApplyResult.ERROR, title

        except PWTimeoutError:
            logger.error("LinkedIn: таймаут при открытии вакансии.")
            if page:
                self.make_shot(page, "timeout")
            return ApplyResult.ERROR, title
        except TargetClosedError:
            logger.error("LinkedIn: окно браузера было неожиданно закрыто.")
            return ApplyResult.ERROR, title
        except Exception as e:
            logger.exception(f"LinkedIn: ошибка при обработке вакансии: {e}")
            if page:
                self.make_shot(page, "error")
            return ApplyResult.ERROR, title
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
