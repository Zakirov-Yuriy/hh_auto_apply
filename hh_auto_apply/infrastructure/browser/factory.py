"""Фабрика клиентов площадок.

Возвращает нужный клиент (hh.ru или LinkedIn) на основе cfg.platform.
Чтобы добавить новую площадку, достаточно реализовать JobBoardClient
и зарегистрировать её здесь.
"""

from __future__ import annotations

from hh_auto_apply.core.config import Config
from hh_auto_apply.infrastructure.browser.base import JobBoardClient


def make_client(cfg: Config) -> JobBoardClient:
    """Создаёт клиент площадки по cfg.platform.

    Args:
        cfg: Конфигурация приложения.

    Returns:
        Экземпляр клиента, реализующего JobBoardClient.

    Raises:
        ValueError: Если указана неизвестная площадка.
    """
    platform = (cfg.platform or "hh").strip().lower()

    if platform in ("hh", "hh.ru", "headhunter"):
        from hh_auto_apply.infrastructure.browser.hh_client import HHClient

        return HHClient(cfg)

    if platform in ("linkedin", "li"):
        from hh_auto_apply.infrastructure.browser.linkedin_client import LinkedInClient

        return LinkedInClient(cfg)

    raise ValueError(
        f"Неизвестная площадка: {cfg.platform!r}. Доступно: 'hh', 'linkedin'."
    )
