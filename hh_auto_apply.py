# hh_auto_apply.py
import os
import sys
import random
import time
from pathlib import Path
from urllib.parse import urlencode
from typing import Optional, List
from datetime import datetime

from dotenv import load_dotenv
from loguru import logger
from playwright.sync_api import (
    sync_playwright, Page, BrowserContext,
    TimeoutError as PWTimeoutError
)

# =========================
# Настройки и утилиты (DRY)
# =========================

load_dotenv()

SEARCH_QUERY = os.getenv("HH_SEARCH_QUERY", "python разработчик").strip()
REGION_IDS = [r.strip() for r in os.getenv("HH_REGION_IDS", "").split(",") if r.strip()]
REMOTE_ONLY = os.getenv("HH_REMOTE_ONLY", "false").lower() == "true"
MAX_APPLIES = int(os.getenv("HH_MAX_APPLIES", "30"))
MIN_SLEEP = float(os.getenv("HH_MIN_SLEEP", "3"))
MAX_SLEEP = float(os.getenv("HH_MAX_SLEEP", "7"))
PERSIST_DIR = os.getenv("HH_PERSIST_DIR", ".hh_user")

RESUME_MATCH = os.getenv("HH_RESUME_TITLE_MATCH", "Python разработчик").strip().lower()
FAIL_IF_RESUME_NOT_FOUND = os.getenv("HH_FAIL_IF_RESUME_NOT_FOUND", "true").lower() == "true"
REQUIRE_COVER_LETTER = os.getenv("HH_REQUIRE_COVER_LETTER", "true").lower() == "true"

COVER_LETTER_FILE = Path("cover_letter.txt")
BASE_URL = "https://hh.ru"

logger.remove()
logger.add(sys.stdout, level="INFO", colorize=True, format="<level>{message}</level>")

def human_pause(a: float = None, b: float = None):
    """Случайные паузы как у человека — уменьшает риск антибота."""
    a = MIN_SLEEP if a is None else a
    b = MAX_SLEEP if b is None else b
    time.sleep(random.uniform(a, b))

def read_cover_letter() -> str:
    if not COVER_LETTER_FILE.exists():
        logger.error("Не найден cover_letter.txt рядом со скриптом.")
        sys.exit(1)
    txt = COVER_LETTER_FILE.read_text(encoding="utf-8").strip()
    if not txt:
        logger.error("Файл cover_letter.txt пуст.")
        sys.exit(1)
    return txt

def build_search_url(page_num: int = 0) -> str:
    params = {
        "text": SEARCH_QUERY,
        "page": page_num,
        "search_field": ["name", "company_name", "description"],
        "order_by": "relevance",
    }
    if REGION_IDS:
        params["area"] = REGION_IDS
    if REMOTE_ONLY:
        params["schedule"] = "remote"
    return f"{BASE_URL}/search/vacancy?{urlencode(params, doseq=True)}"

def is_visible(locator, timeout=1000) -> bool:
    try:
        locator.first.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:
        return False

def ensure_logged_in(page: Page) -> None:
    page.goto(BASE_URL, wait_until="domcontentloaded")
    selectors = [
        '[data-qa="mainmenu_applicantProfile"]',
        'a[href*="/applicant/resumes"]',
        '[aria-label*="Профиль"]',
    ]
    for sel in selectors:
        if is_visible(page.locator(sel), timeout=1200):
            logger.info("Похоже, уже залогинены.")
            return

    logger.warning("Не обнаружен логин. Пожалуйста, войдите на hh.ru в открывшемся окне.")
    page.goto(BASE_URL + "/account/login", wait_until="domcontentloaded")
    input("После входа нажмите Enter в консоли...")
    page.goto(BASE_URL, wait_until="domcontentloaded")
    human_pause()
    logger.info("Продолжаем работу.")

def list_vacancy_links_on_page(page: Page) -> List[str]:
    links = set()
    cards = page.locator('[data-qa="vacancy-serp__vacancy-title"]')
    count = cards.count()
    for i in range(count):
        try:
            href = cards.nth(i).get_attribute("href")
            if href and href.startswith("http"):
                links.add(href.split("?")[0])
        except Exception:
            continue

    if not links:
        logger.warning("Не нашли стандартные селекторы, пробуем запасной метод.")
        cards_alt = page.locator('a:visible').filter(has_text="Python")
        count_alt = min(cards_alt.count(), 50)
        for i in range(count_alt):
            href = cards_alt.nth(i).get_attribute("href")
            if href and "/vacancy/" in href:
                links.add(href.split("?")[0])
    return list(links)

def get_apply_button(page: Page):
    candidates = [
        page.get_by_role("button", name="Откликнуться"),
        page.get_by_role("link", name="Откликнуться"),
        page.locator('[data-qa="vacancy-response-link-top"]'),
        page.locator('[data-qa="vacancy-sidebar-submit"]'),
        page.locator('button:has-text("Откликнуться")'),
        page.locator('a:has-text("Откликнуться")'),
    ]
    for c in candidates:
        if is_visible(c, timeout=900):
            return c.first
    return None

def already_applied(page: Page) -> bool:
    applied_text_variants = [
        "Отклик отправлен", "Вы откликнулись",
        "Отклик уже отправлен", "Отклик отправлен работодателю"
    ]
    for txt in applied_text_variants:
        if is_visible(page.get_by_text(txt, exact=False), timeout=500):
            return True
    return get_apply_button(page) is None

# ---------- Новое: выбор конкретного резюме по названию ----------
def select_specific_resume(page: Page) -> bool:
    """
    Ищем элемент/плитку/радио с названием резюме, которое содержит RESUME_MATCH (нижний регистр).
    Возвращает True, если удалось выбрать именно его.
    """
    # Варианты контейнеров с резюме
    containers = [
        '[data-qa="resume-select_item"]',      # плитки
        '[data-qa="resume-select"] [data-qa="resume-item"]',
        '[data-qa*="resume"]',
        'label:has-text("-")',  # запасной, часто label содержит название
    ]

    # Сначала пробуем точечный поиск по тексту:
    textual = [
        f'xpath=//div[contains(@data-qa,"resume")][.//text()[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮabcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю", "abcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю"), "{RESUME_MATCH}")]]',
        f'xpath=//label[.//text()[contains(translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮabcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю", "abcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю"), "{RESUME_MATCH}")]]',
        f'xpath=//a[contains(@href,"resume")][contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮabcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю", "abcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю"), "{RESUME_MATCH}")]/ancestor::label|//a[contains(@href,"resume")][contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮabcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю", "abcdefghijklmnopqrstuvwxyzёйцукенгшщзхъфывапролджэячсмитьбю"), "{RESUME_MATCH}")]/ancestor::*[contains(@data-qa,"resume-select_item")]',
    ]
    for sel in textual:
        loc = page.locator(sel)
        if loc.count() > 0 and is_visible(loc, timeout=700):
            try:
                # внутри обычно есть radio
                radio = loc.locator('input[type="radio"]').first
                if radio.count() > 0 and radio.is_visible():
                    radio.check()
                else:
                    loc.first.click()
                logger.info(f'Выбрано резюме по маске: "{RESUME_MATCH}"')
                return True
            except Exception:
                continue

    # Если точечного совпадения не нашли — пробуем перебор контейнеров и искать текст внутри
    for sel in containers:
        items = page.locator(sel)
        n = min(items.count(), 10)
        for i in range(n):
            item = items.nth(i)
            try:
                if not is_visible(item, timeout=400):
                    continue
                text = (item.inner_text() or "").strip().lower()
                if RESUME_MATCH in text:
                    radio = item.locator('input[type="radio"]').first
                    if radio.count() > 0 and radio.is_visible():
                        radio.check()
                    else:
                        item.click()
                    logger.info(f'Выбрано резюме по маске: "{RESUME_MATCH}"')
                    return True
            except Exception:
                continue

    logger.warning(f'Не найдено резюме с маской "{RESUME_MATCH}".')
    return False

def select_any_resume_if_needed(page: Page) -> bool:
    """
    Если конкретное резюме не нашлось, можно выбрать первое доступное.
    Возвращает True, если получилось выбрать хоть какое-то резюме.
    """
    candidates = [
        '[data-qa="resume-select_item"]',
        'input[name="resume"]',
        'input[type="radio"][value*="resume"]',
    ]
    for sel in candidates:
        loc = page.locator(sel)
        if loc.count() > 0 and is_visible(loc, timeout=800):
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

def check_consents_if_needed(page: Page) -> None:
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
                    if is_visible(box, timeout=300) and not box.is_checked():
                        box.check()
                        logger.info("Поставлен чекбокс согласия.")
                except Exception:
                    continue
    except Exception:
        pass

def make_shot(page: Page, tag: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"hh_{tag}_{ts}.png"
    try:
        page.screenshot(path=path, full_page=True)
        logger.warning(f"Скриншот сохранён: {path}")
    except Exception as e:
        logger.warning(f"Не удалось сделать скриншот: {e}")

# ---------- Новое: надёжное заполнение сопроводительного ----------
def fill_cover_letter_with_verification(page: Page, cover_text: str) -> bool:
    """
    Ставит письмо в textarea и проверяет, что оно реально там (input_value()).
    Делает до 3 попыток с разными селекторами и Ctrl+A → ввод.
    """
    # иногда поле сразу видно, иногда надо нажать «Добавить сопроводительное»
    try:
        togglers = [
            page.get_by_role("button", name="Добавить сопроводительное"),
            page.get_by_text("Добавить сопроводительное"),
            page.locator('[data-qa="vacancy-response-letter-toggle"]'),
        ]
        for t in togglers:
            if is_visible(t, timeout=800):
                t.first.click()
                human_pause(0.3, 0.6)
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
                if not is_visible(ta, timeout=900):
                    continue
                ta.click()
                # Ctrl+A → ввод
                page.keyboard.press("Control+A")
                ta.fill(cover_text)
                human_pause(0.2, 0.4)
                val = ta.input_value().strip()
                if len(val) >= min(20, len(cover_text) // 2):  # базовая проверка объёма
                    logger.info("Сопроводительное письмо заполнено и подтверждено.")
                    return True
            except Exception:
                continue
        # маленькая пауза и повтор
        human_pause(0.4, 0.8)

    logger.warning("Не удалось подтвердить наличие сопроводительного письма в форме.")
    return False

def add_cover_letter_and_submit(page: Page, cover_text: str) -> bool:
    """
    Вставляем сопроводительное, выбираем нужное резюме, ставим согласия, кладём отклик.
    Учитываем флаги REQUIRE_COVER_LETTER и FAIL_IF_RESUME_NOT_FOUND.
    """
    # 1) Сопроводительное
    letter_ok = fill_cover_letter_with_verification(page, cover_text)
    if REQUIRE_COVER_LETTER and not letter_ok:
        make_shot(page, "no_cover_letter")
        logger.warning("Отклик не отправляем: сопроводительное не удалось вставить (REQUIRE_COVER_LETTER=true).")
        return False

    # 2) Выбор резюме по названию
    selected_exact = select_specific_resume(page)
    if not selected_exact:
        if FAIL_IF_RESUME_NOT_FOUND:
            make_shot(page, "resume_not_found")
            logger.warning("Отклик не отправляем: нужное резюме не найдено (FAIL_IF_RESUME_NOT_FOUND=true).")
            return False
        else:
            select_any_resume_if_needed(page)

    # 3) Чекбоксы согласий
    check_consents_if_needed(page)

    # 4) Поиск активной кнопки и отправка
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
                if is_visible(btn, timeout=900):
                    disabled = btn.get_attribute("disabled")
                    aria = btn.get_attribute("aria-disabled")
                    if not disabled and (aria is None or aria == "false"):
                        return btn
            except Exception:
                continue
        return None

    for attempt in range(3):
        btn = find_enabled_submit()
        if btn:
            try:
                btn.scroll_into_view_if_needed()
            except Exception:
                pass
            human_pause()
            try:
                btn.click()
                page.wait_for_timeout(1500)
                if already_applied(page):
                    logger.success("Отклик отправлен ✅")
                    return True
                page.wait_for_timeout(1500)
                if already_applied(page):
                    logger.success("Отклик отправлен ✅")
                    return True
            except Exception as e:
                logger.warning(f"Клик по кнопке отправки не удался: {e}")
        else:
            # повторно «шевелим» форму (часто после выбора/чекбоксов кнопка активируется не сразу)
            if not selected_exact:
                # вдруг к этому моменту нужное резюме стало видно — ещё попытка
                if select_specific_resume(page):
                    selected_exact = True
            check_consents_if_needed(page)
            human_pause(1, 2)

    logger.warning("Не удалось отправить отклик (возможно, капча или обязательные поля).")
    make_shot(page, "submit_fail")
    return False

def apply_to_vacancy(context: BrowserContext, url: str, cover_text: str) -> bool:
    logger.info(f"Открываю вакансию: {url}")
    page = context.new_page()
    page.on("console", lambda msg: logger.debug(f"[browser] {msg.type} {msg.text}"))

    try:
        page.set_default_timeout(30000)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        human_pause()

        if already_applied(page):
            logger.info("Отклик уже был отправлен — пропускаю.")
            page.close()
            return False

        apply_btn = get_apply_button(page)
        if apply_btn:
            try:
                apply_btn.click()
            except Exception:
                pass
            page.wait_for_timeout(1000)

        success = add_cover_letter_and_submit(page, cover_text)
        page.close()
        return success

    except PWTimeoutError:
        logger.error("Таймаут при открытии вакансии.")
        try:
            make_shot(page, "vacancy_timeout")
        except Exception:
            pass
        page.close()
        return False
    except Exception as e:
        logger.exception(f"Ошибка при обработке вакансии: {e}")
        try:
            slug = url.split("/")[-1][:30]
            make_shot(page, f"error_{slug}")
        except Exception:
            pass
        page.close()
        return False

def main():
    cover_text = read_cover_letter()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PERSIST_DIR,
            headless=False,
            args=["--start-maximized"],
            viewport={"width": 1366, "height": 900},
            slow_mo=50,
        )
        page = context.new_page()
        page.set_default_timeout(30000)
        page.on("console", lambda msg: logger.debug(f"[browser] {msg.type} {msg.text}"))

        ensure_logged_in(page)

        applies_done = 0
        page_num = 0

        while applies_done < MAX_APPLIES:
            search_url = build_search_url(page_num)
            logger.info(f"Страница поиска: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            human_pause()

            links = list_vacancy_links_on_page(page)
            if not links:
                logger.info("Ссылок не найдено. Завершаю.")
                break

            logger.info(f"Найдено вакансий на странице: {len(links)}")

            for vurl in links:
                if applies_done >= MAX_APPLIES:
                    break
                success = apply_to_vacancy(context, vurl, cover_text)
                if success:
                    applies_done += 1
                human_pause()

            page_num += 1

        logger.info(f"Готово. Успешных откликов: {applies_done}")
        context.close()

if __name__ == "__main__":
    main()
