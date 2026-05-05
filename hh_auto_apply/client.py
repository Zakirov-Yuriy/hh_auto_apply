from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlencode

from loguru import logger
from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeoutError
from playwright._impl._errors import TargetClosedError
import requests
import json

from hh_auto_apply.config import Config
from hh_auto_apply.domain import ApplyResult
from hh_auto_apply.selectors import Selectors
from hh_auto_apply.utils import human_pause


class APIKeyRotator:
    """Управляет ротацией API ключей для OpenRouter.
    
    При ошибке с одним ключом автоматически переключается на следующий.
    """
    
    def __init__(self, api_keys: List[str]):
        """Инициализация ротатора с списком API ключей.
        
        Args:
            api_keys: Список OpenRouter API ключей
        """
        if not api_keys:
            raise ValueError("Необходимо передать хотя бы один API ключ")
        
        self.api_keys = api_keys
        self.current_index = 0
        logger.info(f"Инициализирован ротатор с {len(api_keys)} ключом(ами)")
    
    def get_current_key(self) -> str:
        """Получить текущий API ключ."""
        return self.api_keys[self.current_index]
    
    def rotate_to_next(self) -> str:
        """Переключиться на следующий API ключ.
        
        Returns:
            Новый текущий API ключ
        """
        old_index = self.current_index
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        
        if self.current_index == old_index and len(self.api_keys) == 1:
            logger.error("Остался только один API ключ и он выдал ошибку!")
            raise ValueError("Все API ключи исчерпаны")
        
        logger.warning(f"Переключение на следующий API ключ (#{self.current_index + 1}/{len(self.api_keys)})")
        return self.get_current_key()
    
    def has_multiple_keys(self) -> bool:
        """Проверить, есть ли несколько ключей для ротации."""
        return len(self.api_keys) > 1


class HHClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        Path(cfg.screenshots_dir).mkdir(parents=True, exist_ok=True)
        
        # Инициализируем ротатор ключей если они есть
        if cfg.openrouter_api_keys:
            self.key_rotator = APIKeyRotator(cfg.openrouter_api_keys)
        else:
            self.key_rotator = None

    # --------- Вспомогательные методы UI ---------
    @staticmethod
    def is_visible(locator, timeout: int = 1000) -> bool:
        try:
            locator.first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    def _get_job_type_folder(self) -> str:
        """Определяет подпапку для скриншотов на основе search_query.
        
        Returns:
            Название подпапки (flutter, python, или other)
        """
        search_query = self.cfg.search_query.lower()
        if "flutter" in search_query:
            return "flutter"
        elif "python" in search_query:
            return "python"
        else:
            return "other"

    def make_shot(self, page: Page, tag: str) -> None:
        """Сохраняет скриншот вакансии в папку, соответствующую типу.
        
        Args:
            page: Playwright Page объект
            tag: Тег для идентификации типа скриншота (error, timeout, и т.д.)
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"hh_{tag}_{ts}.png"
        
        # Определяем тип вакансии и создаём папку
        job_type = self._get_job_type_folder()
        screenshots_path = Path(self.cfg.screenshots_dir) / job_type
        screenshots_path.mkdir(parents=True, exist_ok=True)
        
        path = str(screenshots_path / fname)
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
            Selectors.LOGIN_PROFILE_LINK,
            Selectors.LOGIN_RESUMES_LINK,
            Selectors.LOGIN_PROFILE_ARIA,
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
            Selectors.VACANCY_LIST_TITLE,
            Selectors.VACANCY_LIST_TITLE_SERP,
            Selectors.VACANCY_LIST_TITLE_BLOKO,
        ]
        for sel in selectors:
            cards = page.locator(sel)
            for i in range(cards.count()):
                href = cards.nth(i).get_attribute("href")
                if href and "/vacancy/" in href:
                    links.add(href.split("?")[0])

        if not links:
            wrappers = page.locator(Selectors.VACANCY_LIST_WRAPPER)
            for i in range(min(wrappers.count(), 60)):
                a = wrappers.nth(i).locator(Selectors.VACANCY_LINK_IN_WRAPPER)
                if a.count():
                    href = a.first.get_attribute("href")
                    if href:
                        links.add(href.split("?")[0])

        if not links:
            logger.warning("Не нашли стандартные селекторы, пробуем запасной метод.")
            cards_alt = page.locator(Selectors.VISIBLE_VACANCY_LINK)
            for i in range(min(cards_alt.count(), 80)):
                href = cards_alt.nth(i).get_attribute("href")
                if href:
                    links.add(href.split("?")[0])

        return list(links)

    def _get_vacancy_description(self, page: Page) -> str:
        description_selectors = [
            'div[data-qa="vacancy-description"]',
            'div[data-qa="job-description"]',
            'div[class*="vacancy-description"]',
            'div[class*="job-description"]',
            'div[data-qa="description-text"]',
            'div[class*="description-text"]',
            'div[data-qa="vacancy-content"]',
            'div[class*="vacancy-content"]',
            'div[class*="content"]',
        ]
        for sel in description_selectors:
            try:
                desc_element = page.locator(sel)
                if desc_element.count() > 0 and self.is_visible(desc_element, timeout=500):
                    text = desc_element.inner_text()
                    if text and len(text.strip()) > 50:  # Ensure it's a substantial description
                        return text.strip()
            except Exception:
                continue
        logger.warning("Не удалось найти описание вакансии.")
        return ""

    def _generate_cover_letter(self, job_description: str) -> str:
        """Генерирует сопроводительное письмо используя OpenRouter API с поддержкой ротации ключей."""
        if not self.key_rotator:
            logger.error("Ротатор ключей не инициализирован. Проверьте OPENROUTER_API_KEY в .env")
            return ""
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        
        try:
            prompt_template = self.cfg.ai_prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error(f"Файл с промптом не найден: {self.cfg.ai_prompt_path}")
            return ""

        final_prompt = prompt_template.format(job_description=job_description)

        data = {
            "model": self.cfg.ai_model,
            "messages": [
                {"role": "user", "content": final_prompt}
            ],
            "max_tokens": 300,
            "temperature": 0.7,
        }
        
        # Попытаемся использовать текущий ключ, и если ошибка, перейдём на следующий
        max_attempts = len(self.key_rotator.api_keys) if self.key_rotator.has_multiple_keys() else 1
        
        for attempt in range(max_attempts):
            try:
                current_key = self.key_rotator.get_current_key()
                # Маскируем ключ для логирования
                masked_key = current_key[:20] + "***" if len(current_key) > 20 else "***"
                headers = {
                    "Authorization": f"Bearer {current_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://hh.ru",
                    "X-Title": "HH Auto Apply Bot",
                }
                
                logger.debug(f"Отправка запроса к OpenRouter (ключ: {masked_key}...): {url}, модель: {self.cfg.ai_model}")
                response = requests.post(url, headers=headers, json=data, timeout=60)
                response.raise_for_status()
                
                result = response.json()
                raw_letter = result["choices"][0]["message"]["content"].strip()

                # Убираем технические токены, которые могут добавлять некоторые модели
                clean_letter = raw_letter.replace("<s>", "").replace("</s>", "").replace("[INST]", "").replace("[/INST]", "").strip()

                logger.info("Сопроводительное письмо сгенерировано.")
                return clean_letter
                
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    error_msg += f" | Response: {e.response.text[:200]}"
                logger.warning(f"Ошибка при генерации письма (попытка {attempt + 1}/{max_attempts}): {error_msg}")
                
                # Если есть другие ключи, переключимся на следующий
                if self.key_rotator.has_multiple_keys() and attempt < max_attempts - 1:
                    try:
                        self.key_rotator.rotate_to_next()
                        continue
                    except ValueError:
                        logger.error("Все API ключи исчерпаны")
                        return ""
                else:
                    logger.error(f"Ошибка при генерации сопроводительного письма: {error_msg}")
                    return ""
                    
            except (KeyError, IndexError) as e:
                logger.error(f"Ошибка парсинга ответа от API: {e}")
                return ""
        
        return ""

    def get_apply_button(self, page: Page):
        candidates = [
            page.get_by_role("button", name="Откликнуться"),
            page.get_by_role("link", name="Откликнуться"),
            page.locator(Selectors.APPLY_BUTTON_TOP),
            page.locator(Selectors.APPLY_BUTTON_SIDEBAR),
            page.locator(Selectors.APPLY_BUTTON_ROLE),
            page.locator(Selectors.APPLY_LINK_ROLE),
        ]
        for c in candidates:
            if self.is_visible(c, timeout=900):
                return c.first
        return None

    def already_applied(self, page: Page) -> bool:
        for txt in Selectors.ALREADY_APPLIED_TEXT:
            if self.is_visible(page.get_by_text(txt, exact=False), timeout=500):
                return True
        return self.get_apply_button(page) is None

    def select_specific_resume(self, page: Page, mask: str) -> bool:
        containers = [
            Selectors.RESUME_SELECT_ITEM,
            Selectors.RESUME_SELECT_ITEM_IN_GROUP,
            Selectors.RESUME_GENERIC_QA,
            Selectors.RESUME_LABEL_WITH_TEXT,
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
            Selectors.RESUME_SELECT_ITEM,
            Selectors.RESUME_FALLBACK_INPUT,
            Selectors.RESUME_FALLBACK_RADIO,
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
            Selectors.CONSENT_CHECKBOX_AGREEMENT,
            Selectors.CONSENT_CHECKBOX_QA,
            Selectors.CONSENT_CHECKBOX_REQUIRED,
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
                page.locator(Selectors.COVER_LETTER_TOGGLE),
            ]
            for t in togglers:
                if self.is_visible(t, timeout=800):
                    t.first.click()
                    human_pause(self.cfg, 0.3, 0.6)
                    break
        except Exception:
            pass

        textarea_selectors = [
            Selectors.COVER_LETTER_TEXTAREA,
            Selectors.COVER_LETTER_TEXTAREA_PLACEHOLDER,
            Selectors.COVER_LETTER_TEXTAREA_GENERIC,
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

    def add_cover_letter_and_submit(self, page: Page, cover_text: str) -> bool:
        letter_ok = self.fill_cover_letter_with_verification(page, cover_text)
        if self.cfg.require_cover_letter and not letter_ok:
            self.make_shot(page, "no_cover_letter")
            logger.warning("Отклик не отправляем: сопроводительное не удалось вставить (REQUIRE_COVER_LETTER=true).")
            return False

        selected_exact = self.select_specific_resume(page, self.cfg.resume_match)
        if not selected_exact:
            if self.cfg.fail_if_resume_not_found:
                self.make_shot(page, "resume_not_found")
                logger.warning("Отклик не отправляем: нужное резюме не найдено (FAIL_IF_RESUME_NOT_FOUND=true).")
                # Do not return here, just log and continue to the next vacancy
            else:
                self.select_any_resume_if_needed(page)

        self.check_consents_if_needed(page)

        submit_candidates = [
            Selectors.SUBMIT_BUTTON,
            Selectors.SUBMIT_BUTTON_TEXT_1,
            Selectors.SUBMIT_BUTTON_TEXT_2,
            Selectors.SUBMIT_BUTTON_GENERIC_QA,
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
                human_pause(self.cfg) # Initial pause before click
                try:
                    btn.click(force=True)
                    page.wait_for_timeout(1500) # Wait after click
                    if self.already_applied(page):
                        logger.success("Отклик отправлен ✅")
                        return True
                    page.wait_for_timeout(1500) # Wait again
                    if self.already_applied(page):
                        logger.success("Отклик отправлен ✅")
                        return True
                except Exception as e:
                    logger.warning(f"Клик по кнопке отправки не удался: {e}")
                    # If click failed, try to dismiss potential overlays or retry click
                    human_pause(self.cfg, 2, 4) # Longer pause to allow overlays to disappear
                    try:
                        btn.click(force=True) # Retry click
                        page.wait_for_timeout(1500)
                        if self.already_applied(page):
                            logger.success("Отклик отправлен ✅")
                            return True
                        page.wait_for_timeout(1500)
                        if self.already_applied(page):
                            logger.success("Отклик отправлен ✅")
                            return True
                    except Exception as e_retry:
                        logger.warning(f"Повторный клик по кнопке отправки не удался: {e_retry}")
            else:
                self.check_consents_if_needed(page)
                human_pause(self.cfg, 1, 2)
        logger.warning("Не удалось отправить отклик (возможно, капча или обязательные поля).")
        self.make_shot(page, "submit_fail")
        return False

    def apply_to_vacancy(self, context: BrowserContext, url: str, cover_text: str) -> tuple[ApplyResult, str]:
        logger.info(f"Открываю вакансию: {url}")
        page = None # Initialize page to None
        try:
            page = context.new_page()
            page.on("console", lambda msg: logger.debug(f"[browser] {msg.type} {msg.text}"))
            title = ""
            page.set_default_timeout(30000)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            human_pause(self.cfg)

            title_selectors = [
                Selectors.VACANCY_TITLE_H1,
                Selectors.VACANCY_TITLE_QA,
                Selectors.VACANCY_TITLE_VIEW_QA,
                Selectors.VACANCY_TITLE_CLASS,
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
                # page.close() # Removed this line
                return ApplyResult.SKIPPED_ALREADY_APPLIED, title

            apply_btn = self.get_apply_button(page)
            generated_cover_letter = ""
            if self.cfg.use_ai_cover_letter and self.key_rotator:
                logger.info("Генерация сопроводительного письма с помощью ИИ...")
                job_description = self._get_vacancy_description(page)
                if job_description:
                    generated_cover_letter = self._generate_cover_letter(job_description)
                else:
                    logger.warning("Не удалось получить описание вакансии для генерации письма.")

            final_cover_text = generated_cover_letter if generated_cover_letter else cover_text

            if apply_btn:
                try:
                    apply_btn.click()
                except Exception:
                    pass
                page.wait_for_timeout(1500)

                # --- Обработка модального окна "вакансия в другой стране" ---
                foreign_modal_button = page.locator(Selectors.FOREIGN_COUNTRY_MODAL_BUTTON)
                if self.is_visible(foreign_modal_button, timeout=2000):
                    logger.info("Обнаружено модальное окно о вакансии в другой стране. Подтверждаю.")
                    try:
                        foreign_modal_button.click()
                        page.wait_for_timeout(1500)
                    except Exception as e:
                        logger.warning(f"Не удалось нажать кнопку в модальном окне: {e}")
            # --- Конец обработки модального окна ---

            ok = self.add_cover_letter_and_submit(page, final_cover_text)
            # Removed page.close() here, as it might be closing the context prematurely.
            # The context should be managed by the caller (app.run).
            # page.close()
            return (ApplyResult.SUCCESS, title) if ok else (ApplyResult.ERROR, title)

        except PWTimeoutError:
            logger.error("Таймаут при открытии вакансии.")
            if page: # Check if page is not None before making a screenshot
                try:
                    self.make_shot(page, "vacancy_timeout")
                except Exception:
                    pass
            # Removed page.close() here, as it might be closing the context prematurely.
            # The context should be managed by the caller (app.run).
            #     page.close()
            # except Exception:
            #     pass
            return ApplyResult.ERROR, title
        except TargetClosedError: # Catch TargetClosedError specifically
            logger.error("Browser context was closed unexpectedly.")
            try:
                self.make_shot(page, "context_closed")
            except Exception:
                pass
            return ApplyResult.ERROR, title
        except TargetClosedError: # Catch TargetClosedError specifically
            logger.error("Browser context was closed unexpectedly.")
            try:
                self.make_shot(page, "context_closed")
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
            # Removed page.close() here as well.
            # try:
            #     page.close()
            # except Exception:
            #     pass
            return ApplyResult.ERROR, title
        finally:
            if page: # Ensure page is not None before closing
                try:
                    page.close()
                except Exception as e:
                    logger.warning(f"Не удалось закрыть страницу: {e}")
