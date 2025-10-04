import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger


class SeenRepo:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init(self):
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_vacancies (
                    id TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL
                )
                """
            )
            c.commit()

    def cleanup(self, ttl_days: int):
        if ttl_days <= 0:
            return
        cutoff = (datetime.utcnow() - timedelta(days=ttl_days)).isoformat()
        with self._conn() as c:
            c.execute("DELETE FROM seen_vacancies WHERE first_seen_at < ?", (cutoff,))
            c.commit()

    def is_seen(self, vac_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("SELECT 1 FROM seen_vacancies WHERE id = ?", (vac_id,))
            return cur.fetchone() is not None

    def mark_seen(self, vac_id: str) -> None:
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT OR IGNORE INTO seen_vacancies (id, first_seen_at) VALUES (?, ?)",
                    (vac_id, datetime.utcnow().isoformat()),
                )
                c.commit()
        except Exception:
            logger.debug("mark_seen failed; ignoring")
