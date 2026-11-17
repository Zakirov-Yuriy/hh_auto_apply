"""Универсальная обработка всплывающих окон hh.ru (16.11.2026).

Бот находит любое видимое модальное окно и проходит его сам:
  * выбор города или региона: печатает город из HH_CITY и берёт первую подсказку;
  * выпадающие списки <select>: выбирает город, если он есть в списке, иначе первый вариант;
  * пустые текстовые поля: ответ пишет нейросеть по подписи поля (зарплата берётся из конфига);
  * радиокнопки без выбора: вариант выбирает нейросеть, без неё берётся первый;
  * обязательные чекбоксы: ставит галочку;
  * затем жмёт кнопку подтверждения («Отправить», «Продолжить», «Всё равно откликнуться» и т.д.).

Два исключения:
  * форму самого отклика (резюме, письмо, вопросы работодателя) модуль не трогает,
    её заполняет основной сценарий в hh_client.py;
  * капчу бот не вводит: окно капчи передаётся в wait_for_manual_captcha,
    бот пищит и ждёт, пока человек введёт текст с картинки.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from loguru import logger
from playwright.sync_api import Locator, Page

from hh_auto_apply.infrastructure.browser.selectors import Selectors
from hh_auto_apply.infrastructure.utils import human_pause

if TYPE_CHECKING:  # pragma: no cover
    from hh_auto_apply.infrastructure.browser.hh_client import HHClient


class PopupHandler:
    # Сколько окон подряд проходим за один вызов (окно может открыть следующее).
    MAX_ROUNDS = 6

    def __init__(self, client: "HHClient"):
        self.client = client
        self.cfg = client.cfg
        self._page: Optional[Page] = None
        self._resume_ctx: Optional[Dict[str, str]] = None

    # ------------------------------------------------------------------ public

    def handle(self, page: Page, vacancy_title: str = "") -> int:
        """Проходит все всплывшие окна. Возвращает, сколько окон обработано."""
        self._page = page
        handled = 0
        last_signature = None
        for _ in range(self.MAX_ROUNDS):
            # Капча всегда первой: её «Отправить» нельзя нажимать за человека.
            if self.client.wait_for_manual_captcha(page):
                handled += 1
                continue

            dialog = self._top_dialog(page)
            if dialog is None:
                break
            if self._is_response_form(dialog):
                # Форма отклика: дальше работает основной сценарий.
                break

            signature = self._signature(dialog)
            if signature == last_signature:
                # То же окно после нашего клика: не крутимся вечно.
                logger.warning("Всплывающее окно не закрылось после обработки, оставляю как есть.")
                self.client.make_shot(page, "popup_stuck")
                break
            last_signature = signature

            title = self._dialog_title(dialog)
            logger.info(f"Всплывающее окно: «{title[:80] or 'без заголовка'}». Заполняю.")

            self._fill_city_inputs(page, dialog)
            self._fill_selects(dialog)
            self._fill_text_fields(dialog, title, vacancy_title)
            self._fill_radios(dialog, title, vacancy_title)
            self._check_required_boxes(dialog)

            if not self._click_confirm(dialog):
                logger.warning("В окне не нашлось кнопки подтверждения.")
                self.client.make_shot(page, "popup_no_button")
                break
            handled += 1
            page.wait_for_timeout(1200)
        return handled

    # ----------------------------------------------------------- поиск окна

    def _top_dialog(self, page: Page) -> Optional[Locator]:
        """Последнее видимое модальное окно (оно обычно сверху)."""
        found: Optional[Locator] = None
        for sel in Selectors.POPUP_CONTAINERS:
            try:
                loc = page.locator(sel)
                for i in range(min(loc.count(), 10)):
                    item = loc.nth(i)
                    if item.is_visible():
                        found = item
            except Exception:
                continue
        return found

    def _is_response_form(self, dialog: Locator) -> bool:
        for sel in Selectors.RESPONSE_FORM_MARKERS:
            try:
                if dialog.locator(sel).count() > 0:
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _signature(dialog: Locator) -> str:
        try:
            return (dialog.inner_text(timeout=1000) or "").strip()[:300]
        except Exception:
            return ""

    @staticmethod
    def _dialog_title(dialog: Locator) -> str:
        for sel in ("h1", "h2", "h3", '[data-qa*="title"]', '[role="heading"]'):
            try:
                loc = dialog.locator(sel).first
                if loc.count() and loc.is_visible():
                    txt = (loc.inner_text(timeout=500) or "").strip()
                    if txt:
                        return txt
            except Exception:
                continue
        try:
            return (dialog.inner_text(timeout=500) or "").strip().split("\n")[0]
        except Exception:
            return ""

    # ------------------------------------------------------------ подписи

    @staticmethod
    def _attr(el: Locator, name: str) -> str:
        try:
            return (el.get_attribute(name) or "").strip()
        except Exception:
            return ""

    def _field_label(self, dialog: Locator, el: Locator) -> str:
        """Подпись поля: aria-label, placeholder, <label for>, обёртка <label>."""
        for attr in ("aria-label", "placeholder", "title"):
            val = self._attr(el, attr)
            if val:
                return val
        el_id = self._attr(el, "id")
        if el_id:
            try:
                lab = dialog.locator(f'label[for="{el_id}"]').first
                if lab.count():
                    txt = (lab.inner_text(timeout=500) or "").strip()
                    if txt:
                        return txt
            except Exception:
                pass
        try:
            wrap = el.locator("xpath=ancestor::label[1]")
            if wrap.count():
                txt = (wrap.first.inner_text(timeout=500) or "").strip()
                if txt:
                    return txt
        except Exception:
            pass
        return self._attr(el, "name")

    def _is_captcha_field(self, el: Locator) -> bool:
        blob = " ".join(
            self._attr(el, a) for a in ("placeholder", "name", "data-qa", "aria-label")
        ).lower()
        return "captcha" in blob or "капч" in blob or "с картинки" in blob

    @staticmethod
    def _looks_like_city(text: str) -> bool:
        t = text.lower()
        return any(m in t for m in Selectors.POPUP_CITY_WORDS)

    def _city(self) -> str:
        return (getattr(self.cfg, "hh_city", "") or "Москва").strip()

    # ---------------------------------------------------------- заполнение

    def _visible_items(self, dialog: Locator, selector: str, limit: int = 15) -> List[Locator]:
        out = []
        try:
            loc = dialog.locator(selector)
            for i in range(min(loc.count(), limit)):
                item = loc.nth(i)
                try:
                    if item.is_visible() and item.is_enabled():
                        out.append(item)
                except Exception:
                    continue
        except Exception:
            pass
        return out

    def _fill_city_inputs(self, page: Page, dialog: Locator) -> None:
        for el in self._visible_items(dialog, 'input:not([type]), input[type="text"], input[type="search"]'):
            if self._is_captcha_field(el):
                continue
            label = self._field_label(dialog, el)
            if not self._looks_like_city(label + " " + self._attr(el, "name") + " " + self._attr(el, "data-qa")):
                continue
            try:
                if el.input_value().strip():
                    continue
                city = self._city()
                el.click()
                el.fill("")
                el.type(city, delay=60)
                page.wait_for_timeout(1200)
                if not self._pick_suggestion(page, city):
                    el.press("ArrowDown")
                    el.press("Enter")
                logger.info(f"[окно] Город: {city}")
            except Exception as e:
                logger.warning(f"[окно] Не удалось заполнить город: {e}")

    def _pick_suggestion(self, page: Page, city: str) -> bool:
        for sel in Selectors.POPUP_SUGGEST_ITEMS:
            try:
                items = page.locator(sel)
                n = min(items.count(), 20)
                if not n:
                    continue
                # Сначала точное совпадение с городом, потом первая подсказка.
                for i in range(n):
                    it = items.nth(i)
                    if it.is_visible() and (it.inner_text(timeout=300) or "").strip().lower().startswith(city.lower()):
                        it.click()
                        return True
                first = items.first
                if first.is_visible():
                    first.click()
                    return True
            except Exception:
                continue
        return False

    def _fill_selects(self, dialog: Locator) -> None:
        city = self._city().lower()
        for sel_el in self._visible_items(dialog, "select"):
            try:
                options = sel_el.locator("option")
                values = []
                for i in range(options.count()):
                    opt = options.nth(i)
                    values.append((self._attr(opt, "value"), (opt.inner_text(timeout=300) or "").strip()))
                current = sel_el.input_value()
                if current and current not in ("", "0"):
                    continue
                choice = next((v for v, t in values if v and city in t.lower()), None)
                if choice is None:
                    choice = next((v for v, t in values if v and v != "0"), None)
                if choice is not None:
                    sel_el.select_option(choice)
                    logger.info(f"[окно] Список «{self._field_label(dialog, sel_el)[:40]}»: выбран {choice}")
            except Exception as e:
                logger.warning(f"[окно] Не удалось выбрать значение в списке: {e}")

    def _ask_ai(self, question: str, field_type: str, vacancy_title: str,
                options: Optional[List[Dict]] = None):
        q = {"question": question, "type": field_type, "field_name": "", "options": options or []}
        try:
            if self._resume_ctx is None:
                self._resume_ctx = self.client._extract_resume_context(self._page)
            answered = self.client._generate_answers_for_custom_questions(
                [q], self._resume_ctx, vacancy_title
            )
            return answered[0].get("answer") if answered else None
        except Exception as e:
            logger.warning(f"[окно] Нейросеть не ответила: {e}")
            return None

    def _fill_text_fields(self, dialog: Locator, title: str, vacancy_title: str) -> None:
        selector = (
            'textarea, input:not([type]), input[type="text"], input[type="number"], '
            'input[type="tel"], input[type="email"]'
        )
        for el in self._visible_items(dialog, selector):
            if self._is_captcha_field(el):
                continue
            try:
                if el.input_value().strip():
                    continue
            except Exception:
                continue
            label = self._field_label(dialog, el)
            if self._looks_like_city(label):
                continue  # город уже заполнен в _fill_city_inputs
            question = f"{title}\n{label}".strip() or "Комментарий"
            answer = self._ask_ai(question, "textarea", vacancy_title)
            if not answer:
                logger.warning(f"[окно] Поле «{label[:40]}» осталось пустым: нет ответа нейросети.")
                continue
            if self._attr(el, "type") == "number":
                digits = "".join(ch for ch in str(answer) if ch.isdigit())
                answer = digits or answer
            try:
                el.click()
                el.fill(str(answer))
                logger.info(f"[окно] Поле «{label[:40]}»: {str(answer)[:60]}")
                human_pause(self.cfg, 0.2, 0.4)
            except Exception as e:
                logger.warning(f"[окно] Не удалось заполнить поле «{label[:40]}»: {e}")

    def _fill_radios(self, dialog: Locator, title: str, vacancy_title: str) -> None:
        groups: Dict[str, List[Locator]] = {}
        try:
            radios = dialog.locator('input[type="radio"]')
            for i in range(min(radios.count(), 40)):
                rb = radios.nth(i)
                groups.setdefault(self._attr(rb, "name") or f"_{i}", []).append(rb)
        except Exception:
            return
        for name, items in groups.items():
            try:
                if any(rb.is_checked() for rb in items):
                    continue
                options = []
                for idx, rb in enumerate(items):
                    options.append({"value": self._attr(rb, "value") or str(idx),
                                    "label": self._field_label(dialog, rb)})
                picked = self._ask_ai(title or name, "radio", vacancy_title, options)
                target = next((rb for rb, o in zip(items, options) if o["value"] == str(picked)), items[0])
                target.check(force=True)
                logger.info(f"[окно] Выбран вариант: {self._field_label(dialog, target)[:40]}")
            except Exception as e:
                logger.warning(f"[окно] Не удалось выбрать радиокнопку: {e}")

    def _check_required_boxes(self, dialog: Locator) -> None:
        for sel in ('input[type="checkbox"][required]', 'input[type="checkbox"][aria-required="true"]',
                    Selectors.CONSENT_CHECKBOX_AGREEMENT, Selectors.CONSENT_CHECKBOX_QA):
            try:
                boxes = dialog.locator(sel)
                for i in range(min(boxes.count(), 10)):
                    box = boxes.nth(i)
                    if not box.is_checked():
                        box.check(force=True)
                        logger.info("[окно] Поставлена обязательная галочка.")
            except Exception:
                continue

    # -------------------------------------------------------------- кнопки

    def _click_confirm(self, dialog: Locator) -> bool:
        buttons = self._visible_items(dialog, 'button, [role="button"], input[type="submit"]', limit=30)

        def text_of(btn: Locator) -> str:
            try:
                return ((btn.inner_text(timeout=300) or "") or self._attr(btn, "value")
                        or self._attr(btn, "aria-label")).strip()
            except Exception:
                return self._attr(btn, "aria-label")

        labelled = [(b, text_of(b)) for b in buttons]
        labelled = [(b, t) for b, t in labelled
                    if not any(bad in t.lower() for bad in Selectors.POPUP_NEVER_CLICK)]

        # 1) по тексту в порядке приоритета
        for wanted in Selectors.POPUP_CONFIRM_TEXTS:
            for btn, txt in labelled:
                if txt.lower() == wanted.lower() or txt.lower().startswith(wanted.lower()):
                    return self._click(btn, txt)
        # 2) по data-qa / type=submit
        for btn, txt in labelled:
            qa = self._attr(btn, "data-qa").lower()
            if any(k in qa for k in ("submit", "confirm", "accept", "apply")) or self._attr(btn, "type") == "submit":
                return self._click(btn, txt or qa)
        return False

    def _click(self, btn: Locator, txt: str) -> bool:
        try:
            if self._attr(btn, "disabled") or self._attr(btn, "aria-disabled") == "true":
                logger.warning(f"[окно] Кнопка «{txt}» неактивна: не все поля заполнены.")
                return False
            human_pause(self.cfg, 0.3, 0.7)
            btn.click()
            logger.info(f"[окно] Нажата кнопка «{txt}».")
            return True
        except Exception as e:
            logger.warning(f"[окно] Не удалось нажать «{txt}»: {e}")
            return False
