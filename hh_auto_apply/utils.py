import random
import re
import time

from hh_auto_apply.config import Config

VAC_ID_RE = re.compile(r"/vacancy/(\d+)")


def human_pause(cfg: Config, a: float | None = None, b: float | None = None) -> None:
    a = cfg.min_sleep if a is None else a
    b = cfg.max_sleep if b is None else b
    time.sleep(random.uniform(a, b))


def extract_vacancy_id(url: str) -> str:
    m = VAC_ID_RE.search(url)
    return m.group(1) if m else url.split("/")[-1].split("?")[0]
