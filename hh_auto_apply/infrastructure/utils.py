"""Infrastructure utilities."""

from __future__ import annotations

import random
import re
import time

from hh_auto_apply.core.config import Config

VAC_ID_RE = re.compile(r"/vacancy/(\d+)")


def human_pause(cfg: Config, a: float | None = None, b: float | None = None) -> None:
    """Pause for a random duration between min_sleep and max_sleep.

    Args:
        cfg: Configuration object with min_sleep and max_sleep.
        a: Minimum pause duration (defaults to cfg.min_sleep).
        b: Maximum pause duration (defaults to cfg.max_sleep).
    """
    a = cfg.min_sleep if a is None else a
    b = cfg.max_sleep if b is None else b
    time.sleep(random.uniform(a, b))


def extract_vacancy_id(url: str) -> str:
    """Extract vacancy ID from hh.ru URL.

    Args:
        url: Vacancy URL.

    Returns:
        Vacancy ID as string.
    """
    m = VAC_ID_RE.search(url)
    return m.group(1) if m else url.split("/")[-1].split("?")[0]
