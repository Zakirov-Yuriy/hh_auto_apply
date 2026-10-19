"""Клиент OpenRouter с ротацией ключей и цепочкой запасных моделей.

Вынесен из hh_client.py 19.10.2026, когда бесплатная qwen/qwen3.8-27b:free
исчезла из каталога и бот остался без писем. Бесплатные модели приходят и
уходят, поэтому модель теперь не одна, а список: не ответила первая, берём
следующую.

Три источника ошибки 429 у бесплатных моделей, и лечатся они по-разному:

- ``free-models-per-day``: дневной лимит аккаунта (50 запросов без купленных
  кредитов, 1000 после разовой покупки на 10 долларов). Смена модели не
  поможет, поможет только другой ключ от другого аккаунта.
- ``free-models-per-min``: 20 запросов в минуту на аккаунт. Помогает пауза.
- ``temporarily rate-limited upstream``: общий бесплатный пул провайдера
  переполнен другими пользователями. Пауза не поможет, поможет другая модель.

Что бот говорит человеку (19.10.2026). Раньше при любой беде с нейросетью
в логе была одна строка warning, а бот шёл дальше и помечал вакансии
просмотренными. Теперь:

- ``preflight()`` перед запуском проверяет ключи и модели без траты
  бесплатных запросов и печатает, что именно сломано и что делать;
- мёртвые ключи (401, дневной лимит) и мёртвые модели (платная, удалена)
  запоминаются на весь запуск и больше не дёргаются;
- каждая такая находка печатается рамкой с инструкцией, см. ``banner()``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

import requests
from loguru import logger


CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
KEY_URL = "https://openrouter.ai/api/v1/key"
MODELS_URL = "https://openrouter.ai/api/v1/models"
FREE_MODELS_PAGE = "https://openrouter.ai/models?q=free"

# Пауза при минутном лимите или временной недоступности. Бесплатные модели
# делят поток на всех, через несколько секунд запрос обычно проходит.
RETRY_PAUSE = 15.0

# Сколько раз пробовать одну модель, прежде чем перейти к следующей.
MAX_ATTEMPTS_PER_MODEL = 3

HOW_TO_FIX_KEYS = (
    "Что делать: выпустить новый ключ на openrouter.ai, раздел API Keys, и "
    "вписать в OPENROUTER_API_KEY в .env (несколько ключей через запятую)."
)
HOW_TO_FIX_DAILY = (
    "Что делать: дождаться завтра, добавить ключ от другого аккаунта через "
    "запятую в OPENROUTER_API_KEY, либо один раз пополнить баланс на 10 "
    "долларов (лимит станет 1000 запросов в день)."
)
HOW_TO_FIX_MODELS = (
    f"Что делать: убрать эту модель из AI_MODEL в .env и вписать другую из "
    f"списка бесплатных: {FREE_MODELS_PAGE}"
)


def banner(title: str, *lines: str) -> None:
    """Печатает заметное сообщение в консоль: рамка, заголовок, инструкция.

    Уровень ERROR, чтобы было видно и без --verbose.
    """
    width = 72
    logger.error("=" * width)
    logger.error(title)
    for line in lines:
        if line:
            logger.error(line)
    logger.error("=" * width)


def masked(key: str) -> str:
    """Ключ для лога: начало и три звёздочки, целиком ключ в лог не попадает."""
    return key[:12] + "***" if len(key) > 12 else "***"


class APIKeyRotator:
    """Управляет ротацией API ключей для OpenRouter.

    При ошибке с одним ключом автоматически переключается на следующий.
    Ключи, которые не принимаются или упёрлись в дневной лимит, помечаются
    мёртвыми и до конца запуска не используются.
    """

    def __init__(self, api_keys: List[str]):
        """Инициализация ротатора с списком API ключей.

        Args:
            api_keys: Список OpenRouter API ключей.
        """
        if not api_keys:
            raise ValueError("Необходимо передать хотя бы один API ключ")

        self.api_keys = api_keys
        self.current_index = 0
        self.dead: Dict[str, str] = {}  # ключ -> причина
        logger.info(f"Инициализирован ротатор с {len(api_keys)} ключом(ами)")

    def get_current_key(self) -> str:
        """Получить текущий API ключ."""
        return self.api_keys[self.current_index]

    def alive_keys(self) -> List[str]:
        """Ключи, которые ещё можно использовать."""
        return [k for k in self.api_keys if k not in self.dead]

    def mark_dead(self, key: str, reason: str) -> None:
        """Пометить ключ мёртвым до конца запуска."""
        self.dead[key] = reason

    def rotate_to_next(self) -> str:
        """Переключиться на следующий живой API ключ.

        Returns:
            Новый текущий API ключ.

        Raises:
            ValueError: Если живых ключей, кроме текущего, не осталось.
        """
        total = len(self.api_keys)
        for step in range(1, total):
            candidate = (self.current_index + step) % total
            if self.api_keys[candidate] not in self.dead:
                self.current_index = candidate
                logger.warning(f"Переключение на следующий API ключ (#{candidate + 1}/{total})")
                return self.get_current_key()

        logger.error("Живых API ключей больше нет.")
        raise ValueError("Все API ключи исчерпаны")

    def has_multiple_keys(self) -> bool:
        """Проверить, есть ли несколько ключей для ротации."""
        return len(self.api_keys) > 1


class Verdict(str, Enum):
    """Что делать после очередной попытки."""

    DONE = "done"  # есть текст
    RETRY_SAME = "retry_same"  # подождать и повторить ту же модель тем же ключом
    NEXT_KEY = "next_key"  # сменить ключ, модель оставить
    NEXT_MODEL = "next_model"  # эта модель не поможет, берём следующую
    STOP = "stop"  # дальше пробовать бессмысленно (дневной лимит, все ключи мертвы)


@dataclass(frozen=True)
class Attempt:
    """Результат одной попытки запроса.

    permanent: причина не пройдёт сама (ключ не принят, модель платная), в
    отличие от занятого пула или пустого ответа.
    """

    verdict: Verdict
    text: str = ""
    reason: str = ""
    permanent: bool = False


def _error_text(response: requests.Response) -> str:
    """Собирает текст ошибки из тела ответа OpenRouter, не роняя бот на не-JSON."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]

    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return response.text[:300]

    parts = [str(err.get("message", ""))]
    meta = err.get("metadata") or {}
    if isinstance(meta, dict):
        for name in ("raw", "limit_source", "provider_name"):
            if meta.get(name):
                parts.append(f"{name}={meta[name]}")
    return " | ".join(p for p in parts if p)[:400]


def is_daily_limit(error_text: str) -> bool:
    """Дневной лимит бесплатных запросов, в отличие от минутного или upstream."""
    text = error_text.lower()
    return "per-day" in text or "per day" in text or "daily" in text


def classify_rate_limit(error_text: str) -> Verdict:
    """Разбирает 429 по тексту ошибки OpenRouter.

    Формулировки взяты из реальных ответов 19.10.2026. Если OpenRouter их
    поменяет, в худшем случае мы подождём и повторим, то есть вернёмся к
    старому поведению бота.
    """
    text = error_text.lower()

    if is_daily_limit(text):
        return Verdict.NEXT_KEY

    if "upstream" in text or "provider returned error" in text:
        return Verdict.NEXT_MODEL

    return Verdict.RETRY_SAME


def classify_response(response: requests.Response) -> Attempt:
    """Переводит HTTP-ответ в решение: взять текст, повторить, сменить ключ или модель."""
    status = response.status_code

    if status == 200:
        try:
            payload = response.json()
        except ValueError:
            return Attempt(Verdict.RETRY_SAME, reason="ответ 200, но не JSON")

        if not isinstance(payload, dict):
            return Attempt(Verdict.RETRY_SAME, reason="ответ 200, но неожиданный формат")

        # OpenRouter иногда кладёт ошибку в тело с кодом 200.
        if payload.get("error"):
            err = payload["error"]
            code = err.get("code") if isinstance(err, dict) else None
            message = str(err.get("message", err)) if isinstance(err, dict) else str(err)
            if code == 429:
                return Attempt(classify_rate_limit(message), reason=f"429 в теле: {message[:200]}")
            return Attempt(Verdict.NEXT_MODEL, reason=f"ошибка в теле ответа: {message[:200]}")

        choices = payload.get("choices") or []
        message = (choices[0].get("message") or {}) if choices else {}
        text = (message.get("content") or "").strip()
        if text:
            return Attempt(Verdict.DONE, text=text)

        # Размышляющая модель могла потратить все токены на раздумья и
        # вернуть пустоту. Повторять ту же модель нет смысла.
        finish = choices[0].get("finish_reason") if choices else None
        return Attempt(
            Verdict.NEXT_MODEL,
            reason=f"модель вернула пустой текст (причина завершения: {finish})",
        )

    error_text = _error_text(response)

    if status == 429:
        verdict = classify_rate_limit(error_text)
        return Attempt(verdict, reason=f"429: {error_text}", permanent=verdict == Verdict.NEXT_KEY)

    if status == 401:
        return Attempt(
            Verdict.NEXT_KEY, reason=f"401, ключ не принят: {error_text}", permanent=True
        )

    if status == 402:
        return Attempt(
            Verdict.NEXT_MODEL,
            reason=f"402, модель больше не бесплатная: {error_text}",
            permanent=True,
        )

    if status == 404 and "data policy" in error_text.lower():
        # Настройка аккаунта, а не модели: без разрешения обучаться на
        # запросах бесплатные модели недоступны все разом.
        return Attempt(
            Verdict.STOP,
            reason="OpenRouter не даёт бесплатные модели: в настройках аккаунта, "
            "раздел Privacy, не разрешено обучение на запросах",
        )

    if status in (400, 403, 404):
        return Attempt(Verdict.NEXT_MODEL, reason=f"{status}: {error_text}", permanent=True)

    # 5xx, 408 и прочее: провайдер прилёг, пробуем ещё раз.
    return Attempt(Verdict.RETRY_SAME, reason=f"{status}: {error_text}")


@dataclass
class KeyStatus:
    """Состояние одного ключа по данным GET /api/v1/key."""

    key: str
    ok: bool
    note: str = ""
    daily_used: Optional[int] = None
    daily_limit: Optional[int] = None
    daily_remaining: Optional[int] = None


@dataclass
class PreflightReport:
    """Итог проверки перед запуском: что с ключами и моделями."""

    keys: List[KeyStatus] = field(default_factory=list)
    available_models: List[str] = field(default_factory=list)
    missing_models: Dict[str, str] = field(default_factory=dict)  # модель -> что с ней
    catalog_checked: bool = False

    @property
    def ok(self) -> bool:
        has_key = any(
            k.ok and (k.daily_remaining is None or k.daily_remaining > 0) for k in self.keys
        )
        has_model = bool(self.available_models) or not self.catalog_checked
        return has_key and has_model

    @property
    def daily_remaining_total(self) -> Optional[int]:
        values = [k.daily_remaining for k in self.keys if k.ok and k.daily_remaining is not None]
        return sum(values) if values else None


class OpenRouterClient:
    """Запросы к OpenRouter: ротация ключей плюс цепочка запасных моделей."""

    def __init__(
        self,
        api_keys: List[str],
        models: List[str],
        timeout: int = 120,
        retry_pause: float = RETRY_PAUSE,
        sleep: Callable[[float], None] = time.sleep,
        post: Callable[..., requests.Response] = requests.post,
        get: Callable[..., requests.Response] = requests.get,
    ):
        """
        Args:
            api_keys: Ключи OpenRouter, перебираются при ошибках ключа.
            models: Модели в порядке предпочтения, перебираются при ошибках модели.
            timeout: Таймаут одного HTTP-запроса, секунды. Бесплатные модели
                отвечают за 8-65 секунд (замеры 19.10.2026), поэтому 120.
            retry_pause: Пауза перед повтором при минутном лимите, секунды.
            sleep: Функция ожидания, подменяется в тестах.
            post: Функция HTTP POST, подменяется в тестах.
            get: Функция HTTP GET для проверок, подменяется в тестах.
        """
        if not models:
            raise ValueError("Необходимо указать хотя бы одну модель")

        self.key_rotator = APIKeyRotator(api_keys)
        self.models = [m.strip() for m in models if m.strip()]
        self.timeout = timeout
        self.retry_pause = retry_pause
        self._sleep = sleep
        self._post = post
        self._get = get
        # Модели, которые в этом запуске больше не пробуем: модель -> причина.
        self.dead_models: Dict[str, str] = {}
        # Причина, по которой запросы остановлены до конца запуска (дневной
        # лимит, data policy). Пока она есть, в сеть не ходим: каждая
        # вакансия иначе ждала бы отказ заново.
        self.stopped_reason: Optional[str] = None
        # Счётчики для итогового отчёта.
        self.answered: Dict[str, int] = {}

    @property
    def api_keys(self) -> List[str]:
        return self.key_rotator.api_keys

    # ------------------------------------------------------------------
    # Проверка перед запуском
    # ------------------------------------------------------------------

    def preflight(self) -> PreflightReport:
        """Проверяет ключи и модели до первого письма, без траты лимита.

        GET /api/v1/key показывает, принимается ли ключ и сколько бесплатных
        запросов осталось сегодня. GET /api/v1/models (без ключа) показывает,
        есть ли модели из AI_MODEL в каталоге и бесплатны ли они ещё.
        Эти запросы в дневной лимит не входят.
        """
        report = PreflightReport()

        for key in self.api_keys:
            report.keys.append(self._check_key(key))

        catalog = self._fetch_catalog()
        if catalog is not None:
            report.catalog_checked = True
            for model in self.models:
                problem = self._model_problem(model, catalog)
                if problem:
                    report.missing_models[model] = problem
                else:
                    report.available_models.append(model)

        self._announce_preflight(report)
        return report

    def _check_key(self, key: str) -> KeyStatus:
        try:
            response = self._get(KEY_URL, headers={"Authorization": f"Bearer {key}"}, timeout=20)
        except requests.exceptions.RequestException as e:
            return KeyStatus(key=key, ok=False, note=f"нет связи с OpenRouter: {e}")

        if response.status_code == 401:
            return KeyStatus(key=key, ok=False, note="ключ не принят (401)")
        if response.status_code != 200:
            return KeyStatus(key=key, ok=False, note=f"ответ {response.status_code}")

        try:
            data = response.json().get("data") or {}
        except (ValueError, AttributeError):
            return KeyStatus(key=key, ok=False, note="непонятный ответ OpenRouter")

        daily = data.get("free_model_daily_requests") or {}
        status = KeyStatus(
            key=key,
            ok=True,
            daily_used=daily.get("used"),
            daily_limit=daily.get("limit"),
            daily_remaining=daily.get("remaining"),
        )
        if status.daily_remaining == 0:
            status.note = "дневной лимит бесплатных запросов исчерпан"
        return status

    def _fetch_catalog(self) -> Optional[Dict[str, dict]]:
        """Каталог моделей OpenRouter: id -> запись. None, если не достучались."""
        try:
            response = self._get(MODELS_URL, timeout=30)
            if response.status_code != 200:
                logger.warning(f"Каталог моделей OpenRouter недоступен: {response.status_code}")
                return None
            items = response.json().get("data") or []
        except (requests.exceptions.RequestException, ValueError, AttributeError) as e:
            logger.warning(f"Каталог моделей OpenRouter не прочитан: {e}")
            return None
        return {m.get("id", ""): m for m in items if isinstance(m, dict)}

    @staticmethod
    def _model_problem(model: str, catalog: Dict[str, dict]) -> str:
        """Пустая строка, если модель есть и бесплатна; иначе описание беды."""
        entry = catalog.get(model)
        if entry is None:
            paid = model[: -len(":free")] if model.endswith(":free") else ""
            if paid and paid in catalog:
                return "бесплатной версии больше нет, осталась только платная " + paid
            return "модели нет в каталоге OpenRouter"

        pricing = entry.get("pricing") or {}
        try:
            prompt_price = float(pricing.get("prompt") or 0)
            completion_price = float(pricing.get("completion") or 0)
        except (TypeError, ValueError):
            return ""
        if prompt_price > 0 or completion_price > 0:
            return "модель стала платной"
        return ""

    def _announce_preflight(self, report: PreflightReport) -> None:
        for n, status in enumerate(report.keys, 1):
            if status.ok and status.daily_remaining is not None:
                logger.info(
                    f"Ключ #{n} ({masked(status.key)}): осталось {status.daily_remaining} "
                    f"из {status.daily_limit} бесплатных запросов сегодня"
                )
            elif status.ok:
                logger.info(f"Ключ #{n} ({masked(status.key)}): принят")
            else:
                logger.warning(f"Ключ #{n} ({masked(status.key)}): {status.note}")
            if not status.ok and "401" in status.note:
                self.key_rotator.mark_dead(status.key, status.note)
            if status.daily_remaining == 0:
                self.key_rotator.mark_dead(status.key, status.note)

        for model, problem in report.missing_models.items():
            self.dead_models[model] = problem
            logger.warning(f"Модель {model}: {problem}")
        for model in report.available_models:
            logger.info(f"Модель {model}: в каталоге, бесплатная")

        dead_keys = [k for k in report.keys if not k.ok and "401" in k.note]
        if dead_keys and len(dead_keys) == len(report.keys):
            banner("НЕЙРОСЕТЬ НЕДОСТУПНА: ни один ключ OpenRouter не принят.", HOW_TO_FIX_KEYS)
        elif dead_keys:
            banner(
                f"Ключи OpenRouter не приняты: {len(dead_keys)} из {len(report.keys)}. "
                "Бот продолжит на остальных.",
                HOW_TO_FIX_KEYS,
            )

        if report.catalog_checked and not report.available_models:
            banner(
                "НЕЙРОСЕТЬ НЕДОСТУПНА: ни одной модели из AI_MODEL больше нет среди бесплатных.",
                *[f"  {m}: {p}" for m, p in report.missing_models.items()],
                HOW_TO_FIX_MODELS,
            )
        elif report.missing_models:
            banner(
                "Часть моделей из AI_MODEL больше не бесплатная, бот продолжит на остальных.",
                *[f"  {m}: {p}" for m, p in report.missing_models.items()],
                HOW_TO_FIX_MODELS,
            )

        if report.daily_remaining_total == 0:
            banner("НЕЙРОСЕТЬ НЕДОСТУПНА: дневной лимит исчерпан на всех ключах.", HOW_TO_FIX_DAILY)

        if report.ok and not self.key_rotator.alive_keys():
            # Защита от рассинхрона: отчёт говорит ok, а живых ключей нет.
            self.stopped_reason = "все ключи мертвы"

    # ------------------------------------------------------------------
    # Итоговый отчёт
    # ------------------------------------------------------------------

    def report_lines(self) -> List[str]:
        """Строки о нейросети для итогового отчёта бота."""
        lines = []
        total = sum(self.answered.values())
        lines.append(f"Запросов к нейросети (успешных): {total}")
        for model, count in self.answered.items():
            lines.append(f"  {model}: {count}")
        for model, reason in self.dead_models.items():
            lines.append(f"Модель выбыла: {model} ({reason})")
        for key, reason in self.key_rotator.dead.items():
            lines.append(f"Ключ выбыл: {masked(key)} ({reason})")
        if self.stopped_reason:
            lines.append(f"Нейросеть остановлена: {self.stopped_reason}")
        return lines

    # ------------------------------------------------------------------
    # Основной запрос
    # ------------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        timeout: Optional[int] = None,
    ) -> Optional[str]:
        """Получить текст ответа модели на промпт.

        Перебирает живые модели в порядке self.models, для каждой до
        MAX_ATTEMPTS_PER_MODEL попыток с ротацией ключей.

        Returns:
            Текст ответа или None, если ни одна модель не ответила.
        """
        if self.stopped_reason:
            logger.warning(f"Нейросеть недоступна до конца запуска: {self.stopped_reason}")
            return None

        if not self.key_rotator.alive_keys():
            self._stop("живых ключей не осталось", HOW_TO_FIX_KEYS)
            return None

        if self.key_rotator.get_current_key() in self.key_rotator.dead:
            try:
                self.key_rotator.rotate_to_next()
            except ValueError:
                self._stop("живых ключей не осталось", HOW_TO_FIX_KEYS)
                return None

        for model in self.models:
            if model in self.dead_models:
                continue
            attempt = self._run_model(model, prompt, max_tokens, temperature, timeout)
            if attempt.verdict == Verdict.DONE:
                self.answered[model] = self.answered.get(model, 0) + 1
                return attempt.text
            if attempt.verdict == Verdict.STOP:
                self._stop(attempt.reason, self._hint_for(attempt.reason))
                return None
            if attempt.permanent:
                self._retire_model(model, attempt.reason)
            else:
                logger.warning(f"Модель {model} не ответила ({attempt.reason}), беру следующую.")

        if not self.alive_models():
            self._stop(
                "все модели из AI_MODEL выбыли: " + "; ".join(
                    f"{m} ({r})" for m, r in self.dead_models.items()
                ),
                HOW_TO_FIX_MODELS,
            )
            return None

        logger.error(f"Ни одна модель не ответила: {', '.join(self.alive_models())}")
        return None

    def alive_models(self) -> List[str]:
        """Модели, которые в этом запуске ещё пробуем."""
        return [m for m in self.models if m not in self.dead_models]

    def _stop(self, reason: str, hint: str) -> None:
        self.stopped_reason = reason
        banner(f"НЕЙРОСЕТЬ ОСТАНОВЛЕНА: {reason}", hint)

    def _retire_model(self, model: str, reason: str) -> None:
        """Модель выбывает до конца запуска; говорим об этом один раз и громко."""
        self.dead_models[model] = reason
        alive = self.alive_models()
        banner(
            f"Модель {model} выбыла: {reason}",
            f"Осталось моделей в цепочке: {len(alive)}"
            + (f" ({', '.join(alive)})" if alive else ""),
            HOW_TO_FIX_MODELS,
        )

    @staticmethod
    def _hint_for(reason: str) -> str:
        if is_daily_limit(reason):
            return HOW_TO_FIX_DAILY
        if "401" in reason or "ключ" in reason.lower():
            return HOW_TO_FIX_KEYS
        if "privacy" in reason.lower():
            return "Что делать: openrouter.ai, Settings, Privacy, разрешить обучение на запросах."
        return HOW_TO_FIX_MODELS

    def _run_model(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        timeout: Optional[int],
    ) -> Attempt:
        """Все попытки для одной модели. Возвращает DONE, STOP или NEXT_MODEL."""
        # Про размышляющие модели (03.10.2026): размышление выключаем явно,
        # иначе лимит токенов уходит на раздумья, а текст приходит пустым.
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "reasoning": {"enabled": False, "exclude": True},
        }

        last = Attempt(Verdict.NEXT_MODEL, reason="нет попыток")
        for n in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
            key = self.key_rotator.get_current_key()
            last = self._request(model, key, payload, timeout or self.timeout)

            if last.verdict == Verdict.DONE:
                return last

            logger.warning(
                f"Нейросеть не ответила (модель {model}, ключ {masked(key)}, "
                f"попытка {n}/{MAX_ATTEMPTS_PER_MODEL}): {last.reason}"
            )

            if last.verdict in (Verdict.STOP, Verdict.NEXT_MODEL):
                return last

            if last.verdict == Verdict.NEXT_KEY:
                self.key_rotator.mark_dead(key, last.reason)
                logger.warning(f"Ключ {masked(key)} выбыл до конца запуска: {last.reason}")
                try:
                    self.key_rotator.rotate_to_next()
                    continue
                except ValueError:
                    return Attempt(Verdict.STOP, reason=f"{last.reason}. Живых ключей не осталось")

            # RETRY_SAME: ждём и пробуем снова, если попытки ещё остались.
            if n < MAX_ATTEMPTS_PER_MODEL:
                logger.info(f"Жду {self.retry_pause:.0f} секунд и пробую снова.")
                self._sleep(self.retry_pause)

        return Attempt(Verdict.NEXT_MODEL, reason=last.reason)

    def _request(self, model: str, key: str, payload: dict, timeout: int) -> Attempt:
        """Один HTTP-запрос. Сетевые ошибки превращает в RETRY_SAME."""
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://hh.ru",
            "X-Title": "HH Auto Apply Bot",
        }
        logger.debug(f"Запрос к OpenRouter: модель {model}, ключ {masked(key)}")
        started = time.monotonic()
        try:
            response = self._post(CHAT_URL, headers=headers, json=payload, timeout=timeout)
        except requests.exceptions.RequestException as e:
            return Attempt(Verdict.RETRY_SAME, reason=f"сетевая ошибка: {e}")

        attempt = classify_response(response)
        if attempt.verdict == Verdict.DONE:
            logger.info(f"Нейросеть ответила: модель {model}, {time.monotonic() - started:.1f} с")
        return attempt
