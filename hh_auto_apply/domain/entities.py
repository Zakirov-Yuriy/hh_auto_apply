from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ApplyResult(str, Enum):
    SUCCESS = "success"
    SKIPPED_ALREADY_APPLIED = "skipped_already_applied"
    ERROR = "error"


@dataclass
class Stats:
    found_links: int = 0
    skipped_seen: int = 0
    skipped_already: int = 0
    opened: int = 0
    applies_done: int = 0
    errors: int = 0

    def bump(self, key: str, inc: int = 1) -> None:
        setattr(self, key, getattr(self, key) + inc)
