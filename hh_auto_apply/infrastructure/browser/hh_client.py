from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlencode

import json
import time

import requests
from loguru import logger
from playwright._impl._errors import TargetClosedError
from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeoutError

from hh_auto_apply.core.config import Config
from hh_auto_apply.domain.entities import ApplyResult
from hh_auto_apply.infrastructure.ai.vacancy_api import (
    fetch_vacancy,
    format_for_prompt,
)
from hh_auto_apply.infrastructure.browser.selectors import Selectors
from hh_auto_apply.infrastructure.utils import extract_vacancy_id, human_pause


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
    platform = "hh"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        Path(cfg.screenshots_dir).mkdir(parents=True, exist_ok=True)
        
        # Инициализируем ротатор ключей если они есть
        if cfg.openrouter_api_keys:
            self.key_rotator = APIKeyRotator(cfg.openrouter_api_keys)
        else:
            self.key_rotator = None

    def extract_job_id(self, url: str) -> str:
        """Извлекает ID вакансии из URL hh.ru (для базы "уже видел")."""
        return extract_vacancy_id(url)

    # --------- Вспомогательные методы UI ---------
    @staticmethod
    def is_visible(locator, timeout: int = 1000) -> bool:
        try:
            locator.first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    # Слова, по которым узнаём тип поиска. Порядок проверки важен: fullstack
    # ищем раньше php, иначе запрос "fullstack php" ушёл бы в php-промпт.
    FULLSTACK_MARKERS = ("fullstack", "full stack", "full-stack", "фулстек", "фуллстек", "фул стек")
    PHP_MARKERS = ("php", "laravel", "пхп", "ларавел")

    def _get_job_type_folder(self) -> str:
        """Определяет подпапку для скриншотов на основе search_query.

        Returns:
            Название подпапки (flutter, fullstack, php, python или other)
        """
        search_query = self.cfg.search_query.lower()

        if "flutter" in search_query:
            return "flutter"
        if any(marker in search_query for marker in self.FULLSTACK_MARKERS):
            return "fullstack"
        if any(marker in search_query for marker in self.PHP_MARKERS):
            return "php"
        if "python" in search_query:
            return "python"

        return "other"

    def _get_prompt_file(self) -> Path:
        """Определяет и возвращает путь к файлу промпта на основе search_query.
        
        Returns:
            Path к файлу промпта (prompt_flutter.txt, prompt_fullstack.txt, prompt_php.txt)
        
        Raises:
            FileNotFoundError: Если ни один файл промпта не найден
        """
        search_query = self.cfg.search_query.lower()

        # Приоритет 1: явно заданный AI_PROMPT_PATH из .env
        explicit = (self.cfg.ai_prompt_path or "").strip()
        if explicit:
            p = Path(explicit)
            # если указано просто имя файла — ищем его в каталоге промптов
            if not p.is_absolute() and p.parent == Path("."):
                p = self.cfg.ai_prompts_dir / p
            if p.exists():
                logger.info(f"Использую промпт из AI_PROMPT_PATH: {p}")
                return p
            logger.warning(
                f"AI_PROMPT_PATH указывает на несуществующий файл: {p}. "
                f"Откатываюсь на автовыбор по search_query."
            )

        # Приоритет 2: автовыбор по типу поиска.
        #
        # Порядок тот же, что в _get_job_type_folder, и он важен: fullstack
        # проверяется раньше php, иначе запрос "fullstack php" ушёл бы в
        # php-промпт.
        by_type = {
            "flutter": "prompt_flutter.txt",
            "fullstack": "prompt_fullstack.txt",
            "php": "prompt_php.txt",
            "python": "prompt_python.txt",
        }

        job_type = self._get_job_type_folder()

        if job_type in by_type:
            prompt_file = self.cfg.ai_prompts_dir / by_type[job_type]
            if prompt_file.exists():
                logger.debug(f"Найден промпт по типу поиска {job_type}: {prompt_file}")
                return prompt_file


        # Fallback: ищем generic prompt файл
        generic_prompt = self.cfg.ai_prompts_dir / "prompt.txt"
        if generic_prompt.exists():
            logger.warning(f"Используется generic промпт: {generic_prompt}")
            return generic_prompt
        
        # Если ничего не найдено, выбрасываем ошибку со списком найденных файлов
        available_files = list(self.cfg.ai_prompts_dir.glob("prompt*.txt"))
        raise FileNotFoundError(
            f"Файл с промптом не найден. Ищу в {self.cfg.ai_prompts_dir}/\n"
            f"Ожидалось одно из: prompt_flutter.txt, prompt_fullstack.txt, prompt_php.txt\n"
            f"Найденные файлы: {[f.name for f in available_files] or 'нет'}"
        )

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

    def list_vacancies_with_titles(self, page: Page) -> List[tuple[str, str]]:
        """Возвращает список (url, title) пар с поисковой страницы.

        В отличие от list_vacancy_links_on_page, который возвращает только URL,
        этот метод также извлекает название вакансии, что нужно для фильтрации
        по стоп-словам ДО открытия страницы вакансии.
        """
        results: list[tuple[str, str]] = []
        seen_urls: set[str] = set()

        selectors = [
            Selectors.VACANCY_LIST_TITLE,
            Selectors.VACANCY_LIST_TITLE_SERP,
            Selectors.VACANCY_LIST_TITLE_BLOKO,
        ]
        for sel in selectors:
            cards = page.locator(sel)
            for i in range(cards.count()):
                try:
                    href = cards.nth(i).get_attribute("href")
                except Exception:
                    continue
                if not href or "/vacancy/" not in href:
                    continue
                clean_url = href.split("?")[0]
                if clean_url in seen_urls:
                    continue
                seen_urls.add(clean_url)
                try:
                    title = (cards.nth(i).inner_text() or "").strip()
                except Exception:
                    title = ""
                results.append((clean_url, title))

        # Fallback если основные селекторы не сработали
        if not results:
            wrappers = page.locator(Selectors.VACANCY_LIST_WRAPPER)
            for i in range(min(wrappers.count(), 60)):
                wrapper = wrappers.nth(i)
                a = wrapper.locator(Selectors.VACANCY_LINK_IN_WRAPPER)
                if not a.count():
                    continue
                try:
                    href = a.first.get_attribute("href")
                except Exception:
                    continue
                if not href:
                    continue
                clean_url = href.split("?")[0]
                if clean_url in seen_urls:
                    continue
                seen_urls.add(clean_url)
                try:
                    title = (a.first.inner_text() or "").strip()
                except Exception:
                    title = ""
                results.append((clean_url, title))

        return results

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

    def _fetch_job_description(self, page: Page, url: str) -> str:
        """Получает описание вакансии.

        Сначала пробует HH API (даёт ключевые навыки = ATS-теги отдельно),
        при неудаче откатывается на парсинг DOM. Если включено
        HH_USE_API_FIRST=false в .env, сразу идёт на DOM.
        """
        if self.cfg.use_hh_api_first:
            try:
                vacancy_id = extract_vacancy_id(url)
                vacancy = fetch_vacancy(
                    vacancy_id,
                    user_agent=self.cfg.hh_api_user_agent,
                )
                if vacancy:
                    skills_count = len(vacancy.get("key_skills") or [])
                    logger.info(
                        f"HH API: получены данные вакансии "
                        f"(ключевых навыков: {skills_count})"
                    )
                    return format_for_prompt(vacancy)
                logger.info("HH API не вернул данных, откат на парсинг DOM.")
            except Exception as e:
                logger.warning(f"Ошибка при обращении к HH API: {e}. Откат на DOM.")

        return self._get_vacancy_description(page)

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
            prompt_file = self._get_prompt_file()
            prompt_template = prompt_file.read_text(encoding="utf-8")
            logger.info(f"Генерация сопроводительного письма с помощью ИИ (файл: {prompt_file.name})")
        except FileNotFoundError as e:
            logger.error(str(e))
            return ""
        except Exception as e:
            logger.error(f"Ошибка при чтении файла промпта: {e}")
            return ""

        final_prompt = prompt_template.format(job_description=job_description)

        # Про размышляющие модели (03.10.2026).
        #
        # Qwen3.8 и подобные сначала думают про себя, и эти рассуждения тоже
        # едят отведённые токены. При лимите в 1000 модель успевала только
        # подумать, а поле с текстом письма возвращала пустым, и бот падал на
        # попытке обрезать пробелы у пустоты.
        #
        # Поэтому: размышление выключаем явно, а запас токенов поднимаем. Письмо
        # у нас 150-200 слов, но промпт длинный, и ответу нужен воздух.
        data = {
            "model": self.cfg.ai_model,
            "messages": [
                {"role": "user", "content": final_prompt}
            ],
            "max_tokens": 4000,
            "temperature": 0.7,
            "reasoning": {"enabled": False, "exclude": True},
        }
        
        # Попыток столько, сколько ключей, но не меньше трёх (03.10.2026).
        #
        # Бесплатные модели регулярно отвечают 429: их общий поток поделён на
        # всех желающих. Это не отказ, а просьба подождать, и через несколько
        # секунд запрос обычно проходит. Без повторов на бесплатной модели
        # пропускалась бы половина вакансий.
        RETRY_PAUSE = 15

        max_attempts = max(3, len(self.key_rotator.api_keys))
        
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

                # Читаем ответ бережно: у размышляющих моделей поле с текстом
                # бывает пустым, и раньше бот падал на этом с трассировкой на
                # пол-экрана (03.10.2026).
                choices = result.get("choices") or []
                message = (choices[0].get("message") or {}) if choices else {}
                raw_letter = (message.get("content") or "").strip()

                if not raw_letter:
                    finish = choices[0].get("finish_reason") if choices else None
                    logger.warning(
                        f"Модель вернула пустое письмо (причина завершения: {finish}). "
                        f"Если это повторяется, смените модель в AI_MODEL на ту, что без размышлений."
                    )
                    return ""

                # Убираем технические токены, которые могут добавлять некоторые модели
                clean_letter = raw_letter.replace("<s>", "").replace("</s>", "").replace("[INST]", "").replace("[/INST]", "").strip()

                logger.info("Сопроводительное письмо сгенерировано.")
                return clean_letter
                
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    error_msg += f" | Response: {e.response.text[:200]}"
                logger.warning(f"Ошибка при генерации письма (попытка {attempt + 1}/{max_attempts}): {error_msg}")
                
                is_rate_limit = "429" in error_msg or "Too Many Requests" in error_msg

                if attempt < max_attempts - 1:
                    # Другой ключ пробуем только если он есть. На лимите
                    # провайдера смена ключа не помогает, помогает пауза.
                    if self.key_rotator.has_multiple_keys() and not is_rate_limit:
                        try:
                            self.key_rotator.rotate_to_next()
                            continue
                        except ValueError:
                            logger.error("Все API ключи исчерпаны")
                            return ""

                    if is_rate_limit:
                        logger.info(f"Модель занята, жду {RETRY_PAUSE} секунд и пробую снова.")
                        time.sleep(RETRY_PAUSE)
                        continue

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

    def _collect_resume_rows(self, page: Page) -> list:
        """Собрать карточки резюме с формы отклика.

        Возвращает список кортежей (текст, radio или None, контейнер).
        """
        rows = []

        # 1) Основной путь: radio-кнопки выбора резюме
        radios = page.locator('input[type="radio"]')
        rcount = radios.count()
        if rcount > 0:
            logger.info(f"Найдено radio-кнопок: {rcount}")
            for i in range(min(rcount, 20)):
                radio = radios.nth(i)
                container = radio.locator(
                    'xpath=ancestor::label[1] | ancestor::*[@data-qa="resume-select_item"][1]'
                ).first
                try:
                    if container.count() == 0:
                        container = radio.locator("xpath=..").first
                    text = (container.inner_text() or "").strip()
                except Exception:
                    text = ""
                rows.append((text, radio, container))

        # 2) Fallback: контейнеры с заголовком резюме
        if not rows:
            for sel in ('[data-qa="resume-select_item"]', '[data-qa="resume-title"]'):
                loc = page.locator(sel)
                c = loc.count()
                if c > 0:
                    logger.info(f'Селектор "{sel}" нашёл карточек: {c}')
                    for i in range(min(c, 20)):
                        el = loc.nth(i)
                        try:
                            text = (el.inner_text() or "").strip()
                        except Exception:
                            text = ""
                        rows.append((text, None, el))
                    break

        return rows

    def _expand_resume_list(self, page: Page) -> bool:
        """Раскрыть выпадающий список резюме на форме отклика (03.10.2026).

        Свёрнутым список показывает только текущее резюме, и выбирать не из
        чего. Жмём по видимой карточке и смотрим, прибавилось ли вариантов.

        Returns:
            True, если после клика карточек стало больше.
        """
        selectors = (
            '[data-qa="resume-select"]',
            '[data-qa="resume-select_item"]',
            '[data-qa="resume-title"]',
        )

        def count_rows() -> int:
            total = page.locator('input[type="radio"]').count()
            if total == 0:
                total = page.locator('[data-qa="resume-select_item"]').count()
            if total == 0:
                total = page.locator('[data-qa="resume-title"]').count()
            return total

        before = count_rows()

        for sel in selectors:
            loc = page.locator(sel)
            if loc.count() == 0:
                continue

            try:
                loc.first.click()
                page.wait_for_timeout(800)
            except Exception as e:
                logger.debug(f"Не удалось раскрыть список через {sel}: {e}")
                continue

            after = count_rows()
            if after > before:
                logger.info(f"Раскрыл список резюме: было {before}, стало {after}")
                return True

        logger.info("Список резюме раскрыть не удалось, работаю с тем, что видно.")
        return False

    def select_specific_resume(self, page: Page, mask: str) -> bool:
        mask = (mask or "").strip().lower()
        if not mask:
            logger.warning("Маска резюме пуста, пропускаю выбор.")
            return False

        def norm(s: str) -> str:
            s = (s or "").lower()
            for ch in ("|", "\u2022", "\u00b7", "\u2014", "\u2013", "-", "/", ",", "\n", "\t"):
                s = s.replace(ch, " ")
            return " ".join(s.split())

        mask_norm = norm(mask)
        mask_tokens = [t for t in mask_norm.split() if len(t) > 2]

        rows = self._collect_resume_rows(page)

        # Резюме может быть несколько, а форма показывает одно (03.10.2026).
        #
        # На форме отклика hh.ru резюме выбирается выпадающим списком: свёрнутым
        # виден только текущий вариант. Бот находил одну карточку и выбирал её,
        # какой бы она ни была. У человека с тремя резюме (Flutter, Fullstack,
        # PHP) это значит, что на PHP-вакансию мог уйти Flutter.
        #
        # Поэтому: если карточка одна, пробуем раскрыть список и собрать заново.
        if len(rows) <= 1 and self._expand_resume_list(page):
            rows = self._collect_resume_rows(page)

        if not rows:
            logger.warning("На форме отклика не найдено ни одной карточки резюме.")
            return False

        logger.info(f'Ищу резюме по маске "{mask}" среди {len(rows)} карточек:')

        best_i, best_score = -1, 0.0
        for i, (text, radio, container) in enumerate(rows):
            tnorm = norm(text)
            logger.info(f'  #{i}: "{tnorm[:150]}"')

            if mask_norm and mask_norm in tnorm:
                score = 1.0
            elif mask_tokens:
                hit = sum(1 for tok in mask_tokens if tok in tnorm)
                score = hit / len(mask_tokens)
            else:
                score = 0.0

            if score > best_score:
                best_score, best_i = score, i

        THRESHOLD = 0.6  # достаточно совпадения ~60% значимых слов
        if best_i >= 0 and best_score >= THRESHOLD:
            text, radio, container = rows[best_i]
            try:
                if container is not None and container.count() > 0:
                    container.click()
                elif radio is not None and radio.count() > 0:
                    radio.check(force=True)
                logger.info(f'  >>> ВЫБРАНА карточка #{best_i} (совпадение {best_score:.0%})')
                return True
            except Exception as e:
                logger.warning(f"Не удалось кликнуть карточку #{best_i}: {e}")

        logger.warning(
            f'Не найдено резюме с маской "{mask}". Лучшее совпадение #{best_i} = {best_score:.0%}. '
            f'Попробуй короткую маску в .env, например HH_RESUME_TITLE_MATCH="Python Backend Developer".'
        )
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
                    # Защита: не заполняем письмом поля кастомных вопросов (task_*)
                    ta_name = (ta.get_attribute("name") or "")
                    if ta_name.startswith("task_"):
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
                logger.warning(
                    f'Отклик НЕ отправлен: резюме по маске "{self.cfg.resume_match}" '
                    f'не найдено (FAIL_IF_RESUME_NOT_FOUND=true).'
                )
                return False
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

    def _detect_custom_questions(self, page: Page) -> List[Dict]:
        """Обнаруживает кастомные вопросы на форме отклика.

        Читает все блоки [data-qa="task-body"]. Для каждого определяет:
        - текст вопроса (data-qa="task-question")
        - тип поля: textarea / checkbox / radio
        - варианты ответов с их value (для checkbox / radio)
        - name поля

        Returns:
            Список словарей вида:
            {
                "question": "Есть ли у вас опыт?",
                "type": "checkbox",          # "textarea" | "checkbox" | "radio"
                "field_name": "task_123",    # для textarea — с суффиксом _text
                "options": [                 # только для checkbox / radio
                    {"value": "334283068", "label": "Да"},
                    {"value": "334283069", "label": "Нет"},
                ],
            }
        """
        result = []
        try:
            task_bodies = page.locator('[data-qa="task-body"]')
            count = task_bodies.count()
            logger.debug(f"Найдено блоков task-body: {count}")

            for i in range(count):
                block = task_bodies.nth(i)

                # --- Текст вопроса ---
                question_text = ""
                try:
                    q_div = block.locator('[data-qa="task-question"]').first
                    question_text = (q_div.inner_text() or "").strip()
                except Exception:
                    pass
                if not question_text:
                    logger.debug(f"Блок #{i}: вопрос не найден, пропускаем")
                    continue

                # --- Определяем тип поля ---
                # 1) Textarea
                textareas = block.locator('textarea[name^="task_"]')
                if textareas.count() > 0:
                    field_name = (textareas.first.get_attribute("name") or "").strip()
                    result.append({
                        "question": question_text,
                        "type": "textarea",
                        "field_name": field_name,
                        "options": [],
                    })
                    logger.debug(f"Блок #{i} [textarea] '{question_text[:60]}' -> {field_name}")
                    continue

                # 2) Checkbox
                checkboxes = block.locator('input[type="checkbox"][name^="task_"]')
                if checkboxes.count() > 0:
                    options = []
                    field_name = ""
                    for j in range(checkboxes.count()):
                        cb = checkboxes.nth(j)
                        val = (cb.get_attribute("value") or "").strip()
                        cb_name = (cb.get_attribute("name") or "").strip()
                        if not field_name and cb_name:
                            field_name = cb_name
                        # Ищем label для этого checkbox
                        label_text = ""
                        try:
                            cell = cb.locator("xpath=ancestor::label[1]")
                            if cell.count() > 0:
                                label_text = (cell.first.locator('[data-qa="cell-text-content"]').first.inner_text() or "").strip()
                        except Exception:
                            pass
                        if val and val != "open":
                            options.append({"value": val, "label": label_text})
                    result.append({
                        "question": question_text,
                        "type": "checkbox",
                        "field_name": field_name,
                        "options": options,
                    })
                    logger.debug(f"Блок #{i} [checkbox] '{question_text[:60]}' options={options}")
                    continue

                # 3) Radio
                radios = block.locator('input[type="radio"][name^="task_"]')
                if radios.count() > 0:
                    options = []
                    field_name = ""
                    for j in range(radios.count()):
                        rb = radios.nth(j)
                        val = (rb.get_attribute("value") or "").strip()
                        rb_name = (rb.get_attribute("name") or "").strip()
                        if not field_name and rb_name:
                            field_name = rb_name
                        label_text = ""
                        try:
                            cell = rb.locator("xpath=ancestor::label[1]")
                            if cell.count() > 0:
                                label_text = (cell.first.locator('[data-qa="cell-text-content"]').first.inner_text() or "").strip()
                        except Exception:
                            pass
                        if val and val != "open":
                            options.append({"value": val, "label": label_text})
                    result.append({
                        "question": question_text,
                        "type": "radio",
                        "field_name": field_name,
                        "options": options,
                    })
                    logger.debug(f"Блок #{i} [radio] '{question_text[:60]}' options={options}")

        except Exception as e:
            logger.warning(f"Ошибка при обнаружении кастомных вопросов: {e}")

        return result

    def _extract_resume_context(self, page: Page) -> Dict[str, str]:
        """Извлекает информацию из резюме, видимого на странице.
        
        Returns:
            Словарь с информацией о резюме: title, salary, experience, skills и т.д.
        """
        context = {
            "title": "Python Backend Developer",  # Default
            "salary": "130000",
            "currency": "RUR",
            "experience_years": "3",
            "skills": "Python, Flutter, Full-stack",
            "education": "Higher",
        }
        
        try:
            # Пытаемся извлечь актуальную информацию из страницы
            # Ищем элементы с информацией о должности, опыте, навыках и т.д.
            
            # Попытаемся найти заголовок профессии
            title_selectors = [
                'span[data-qa*="resume"]',
                'div[class*="resume-title"]',
                'h1[class*="title"]',
            ]
            
            for sel in title_selectors:
                try:
                    elem = page.locator(sel).first
                    if elem:
                        text = (elem.inner_text() or "").strip()
                        if text and len(text) > 5 and len(text) < 100:
                            context["title"] = text
                            break
                except Exception:
                    continue
            
            # Ищем зарплату - получаем весь текст страницы и ищем паттерны
            try:
                page_text = page.locator("body").inner_text()
                if "130" in page_text and "₽" in page_text:
                    context["salary"] = "130000"
            except Exception:
                pass
            
            logger.debug(f"Контекст резюме: {context}")
            
        except Exception as e:
            logger.warning(f"Ошибка при извлечении контекста резюме: {e}")
        
        return context

    def _generate_answers_for_custom_questions(
        self,
        questions: List[Dict],
        resume_context: Dict[str, str],
        vacancy_title: str
    ) -> List[Dict]:
        """Генерирует ответы на кастомные вопросы используя OpenRouter API.

        Для каждого вопроса отправляет в AI структурированный запрос,
        включающий текст вопроса, тип поля и варианты ответов (для checkbox/radio).
        AI возвращает JSON с выбранными вариантами или текстом.

        Args:
            questions: Список словарей от _detect_custom_questions
            resume_context: Информация о резюме (должность, зарплата, навыки)
            vacancy_title: Название вакансии

        Returns:
            Тот же список словарей, дополненный ключом "answer":
            - для textarea: {"answer": "текст ответа"}
            - для checkbox: {"answer": ["334283068", "334283069"]}  (список value)
            - для radio: {"answer": "334283074"}  (один value)
        """
        if not self.key_rotator:
            logger.warning("Ротатор ключей не инициализирован. Невозможно генерировать ответы.")
            return questions

        api_url = "https://openrouter.ai/api/v1/chat/completions"
        result_questions = []

        for q in questions:
            q_copy = dict(q)
            question_text = q["question"]
            field_type = q["type"]
            options = q.get("options", [])
            q_low = question_text.lower()

            try:
                # --- Быстрый путь для зарплатного вопроса (только textarea) ---
                salary_markers = (
                    "зарплат", "ожидани", "gross", "net", "сумм", "на руки",
                    " руки", "отталкива", "оклад", "доход", "вилк", "зп",
                    "з/п", "сколько", "желаем", "от какой", "rub", "руб",
                )
                if field_type == "textarea" and any(m in q_low for m in salary_markers):
                    salary_amount = (self.cfg.salary_expectation
                                     or resume_context.get("salary", "130000"))
                    q_copy["answer"] = salary_amount
                    logger.info(f"Зарплатный вопрос: подставляю '{salary_amount}'")
                    result_questions.append(q_copy)
                    continue

                # --- Формируем промпт для AI ---
                resume_info = (
                    f"Должность: {resume_context.get('title')}\n"
                    f"Опыт: {resume_context.get('experience_years')} лет\n"
                    f"Навыки: {resume_context.get('skills')}\n"
                    f"Зарплатные ожидания: {resume_context.get('salary')} руб.\n"
                    f"Образование: {resume_context.get('education')}"
                )

                if field_type == "textarea":
                    answer_prompt = (
                        f"Ты — соискатель работы. Отвечай от первого лица.\n\n"
                        f"Информация о кандидате:\n{resume_info}\n\n"
                        f"Вакансия: {vacancy_title}\n\n"
                        f"Вопрос работодателя:\n{question_text}\n\n"
                        f"Напиши краткий профессиональный ответ (2-4 предложения) от первого лица.\n"
                        f"Верни ТОЛЬКО текст ответа, без пояснений и кавычек."
                    )
                    response_format = "text"
                    max_tokens = 200

                elif field_type in ("checkbox", "radio"):
                    options_str = "\n".join(
                        f'  value="{o["value"]}" label="{o["label"]}"' 
                        for o in options
                    )
                    if field_type == "checkbox":
                        task_hint = (
                            "Можно выбрать один или несколько вариантов.\n"
                            'Верни JSON: {"values": ["value1", "value2"]} — массив выбранных value.\n'
                            'Если ни один не подходит, верни {"values": []}.'
                        )
                    else:
                        task_hint = (
                            "Выбери ровно один вариант.\n"
                            'Верни JSON: {"value": "value1"} — один выбранный value.\n'
                            "Выбери наиболее подходящий вариант обязательно."
                        )
                    answer_prompt = (
                        f"Ты — соискатель работы.\n\n"
                        f"Информация о кандидате:\n{resume_info}\n\n"
                        f"Вакансия: {vacancy_title}\n\n"
                        f"Вопрос работодателя (тип: {field_type}):\n{question_text}\n\n"
                        f"Доступные варианты ответа:\n{options_str}\n\n"
                        f"{task_hint}\n"
                        f"Верни ТОЛЬКО валидный JSON, без пояснений."
                    )
                    response_format = "json"
                    max_tokens = 80

                else:
                    result_questions.append(q_copy)
                    continue

                # --- Запрос к API ---
                data = {
                    "model": self.cfg.ai_model,
                    "messages": [{"role": "user", "content": answer_prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                }

                max_attempts = len(self.key_rotator.api_keys) if self.key_rotator.has_multiple_keys() else 1
                raw_answer = None

                for attempt in range(max_attempts):
                    try:
                        current_key = self.key_rotator.get_current_key()
                        headers = {
                            "Authorization": f"Bearer {current_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://hh.ru",
                            "X-Title": "HH Auto Apply Bot",
                        }
                        response = requests.post(api_url, headers=headers, json=data, timeout=30)
                        response.raise_for_status()
                        raw_answer = response.json()["choices"][0]["message"]["content"].strip()
                        break
                    except requests.exceptions.RequestException as e:
                        logger.warning(f"Ошибка API (попытка {attempt + 1}): {e}")
                        if self.key_rotator.has_multiple_keys() and attempt < max_attempts - 1:
                            try:
                                self.key_rotator.rotate_to_next()
                            except ValueError:
                                break
                    except (KeyError, IndexError) as e:
                        logger.error(f"Ошибка парсинга ответа API: {e}")
                        break

                if raw_answer is None:
                    result_questions.append(q_copy)
                    continue

                # --- Разбираем ответ в зависимости от типа ---
                if response_format == "text":
                    q_copy["answer"] = raw_answer
                    logger.info(f"[textarea] '{question_text[:50]}' -> '{raw_answer[:60]}'")

                else:
                    clean_json = raw_answer.replace("```json", "").replace("```", "").strip()
                    try:
                        parsed = json.loads(clean_json)
                        if field_type == "radio":
                            q_copy["answer"] = str(parsed.get("value", ""))
                            logger.info(f"[radio] '{question_text[:50]}' -> value='{q_copy['answer']}'")
                        else:
                            vals = parsed.get("values", [])
                            q_copy["answer"] = [str(v) for v in vals]
                            logger.info(f"[checkbox] '{question_text[:50]}' -> values={q_copy['answer']}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"Не удалось распарсить JSON ответ: '{clean_json}' ({e})")
                        q_copy["answer"] = [] if field_type == "checkbox" else ""

            except Exception as e:
                logger.warning(f"Ошибка при генерации ответа на вопрос '{question_text[:50]}': {e}")

            result_questions.append(q_copy)

        return result_questions

    def _fill_custom_questions(self, page: Page, questions_with_answers: List[Dict]) -> bool:
        """Заполняет кастомные поля формы сгенерированными ответами.

        Поддерживает три типа полей:
        - textarea: заполняет текстом
        - checkbox: ставит галочки на выбранных вариантах
        - radio: выбирает один вариант

        Args:
            page: Playwright Page объект
            questions_with_answers: Список словарей с ключом "answer"

        Returns:
            True если хотя бы одно поле успешно обработано, False иначе
        """
        if not questions_with_answers:
            logger.debug("Нет ответов для заполнения кастомных полей")
            return True

        filled_count = 0

        for q in questions_with_answers:
            field_name = q.get("field_name", "")
            field_type = q.get("type", "textarea")
            answer = q.get("answer")
            question_text = q.get("question", "")[:60]

            if answer is None:
                logger.debug(f"Нет ответа для поля '{question_text}', пропускаем")
                continue

            try:
                if field_type == "textarea":
                    textarea = page.locator(f'textarea[name="{field_name}"]').first
                    if not self.is_visible(textarea, timeout=800):
                        logger.warning(f"Textarea '{field_name}' не видима")
                        continue
                    textarea.click()
                    page.keyboard.press("Control+A")
                    textarea.fill(str(answer))
                    human_pause(self.cfg, 0.2, 0.4)
                    val = textarea.input_value().strip()
                    if val:
                        logger.info(f"[textarea] '{question_text}' заполнен: '{str(answer)[:60]}'")
                        filled_count += 1
                    else:
                        logger.warning(f"[textarea] '{question_text}' не удалось заполнить")

                elif field_type == "checkbox":
                    selected_values = answer if isinstance(answer, list) else []
                    if not selected_values:
                        logger.info(f"[checkbox] '{question_text}': нет подходящих вариантов")
                        continue
                    for val in selected_values:
                        cb = page.locator(
                            f'input[type="checkbox"][name="{field_name}"][value="{val}"]').first
                        try:
                            if self.is_visible(cb, timeout=500) and not cb.is_checked():
                                cb.check()
                                logger.info(f"[checkbox] '{question_text}': выбран value='{val}'")
                                filled_count += 1
                        except Exception as e:
                            logger.warning(f"[checkbox] Не удалось выбрать value='{val}': {e}")

                elif field_type == "radio":
                    selected_value = str(answer) if answer else ""
                    if not selected_value:
                        logger.warning(f"[radio] '{question_text}': пустой ответ")
                        continue
                    rb = page.locator(
                        f'input[type="radio"][name="{field_name}"][value="{selected_value}"]').first
                    try:
                        if self.is_visible(rb, timeout=500):
                            rb.check()
                            logger.info(f"[radio] '{question_text}': выбран value='{selected_value}'")
                            filled_count += 1
                        else:
                            logger.warning(f"[radio] '{question_text}': value='{selected_value}' не видим")
                    except Exception as e:
                        logger.warning(f"[radio] Не удалось выбрать value='{selected_value}': {e}")

                human_pause(self.cfg, 0.1, 0.3)

            except Exception as e:
                logger.warning(f"Ошибка при заполнении поля '{question_text}': {e}")
                continue

        return filled_count > 0

    def apply_to_vacancy(self, context: BrowserContext, url: str, cover_text: str) -> tuple[ApplyResult, str]:
        logger.info(f"Открываю вакансию: {url}")
        page = None # Initialize page to None
        title = ""  # Initialize title to empty stringё
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
            if self.cfg.use_ai_cover_letter:
                if not self.key_rotator:
                    logger.error(
                        "Включена генерация писем, но ключ OPENROUTER_API_KEY не задан. "
                        "Отклик не отправляю."
                    )
                    return ApplyResult.SKIPPED_FORM_INCOMPLETE, title

                logger.info("Генерация сопроводительного письма с помощью ИИ...")
                job_description = self._fetch_job_description(page, url)
                if job_description:
                    generated_cover_letter = self._generate_cover_letter(job_description)
                else:
                    logger.warning("Не удалось получить описание вакансии для генерации письма.")

            # Запасное письмо идёт в дело, только если генерация ИИ выключена
            # намеренно (03.10.2026).
            #
            # Раньше при любой осечке подставлялся файл cover_letter.txt. Он
            # написан под один стек, и на вакансию другого стека уходило письмо
            # не по адресу: на PHP-вакансию ушло письмо про Flutter. Для
            # кандидата это хуже, чем не откликнуться вовсе.
            if self.cfg.use_ai_cover_letter and not generated_cover_letter:
                logger.error(
                    "ИИ не смог написать письмо для этой вакансии. Отклик не отправляю, "
                    "чтобы не ушло запасное письмо не по стеку."
                )
                return ApplyResult.SKIPPED_FORM_INCOMPLETE, title

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
            
            # --- Обработка кастомных вопросов ---
            human_pause(self.cfg, 0.5, 1.0)
            custom_questions = self._detect_custom_questions(page)
            if custom_questions:
                logger.info(f"Обнаружено {len(custom_questions)} кастомных вопросов. Генерирую ответы...")
                resume_context = self._extract_resume_context(page)
                questions_with_answers = self._generate_answers_for_custom_questions(
                    custom_questions,
                    resume_context,
                    title
                )
                if questions_with_answers:
                    logger.info(f"Заполняю {len(questions_with_answers)} кастомных полей...")
                    self._fill_custom_questions(page, questions_with_answers)
                else:
                    logger.warning("Не удалось сгенерировать ответы на кастомные вопросы")
            # --- Конец обработки кастомных вопросов ---

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