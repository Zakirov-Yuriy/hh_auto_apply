"""Общий интерфейс для площадок поиска работы (hh.ru, LinkedIn и т.д.).

Оркестратор (application/run_session.py) работает только с этим интерфейсом
и не знает, на какой именно площадке он сейчас откликается. Это позволяет
добавлять новые площадки без изменения логики основного цикла.
"""

from __future__ import annotations

from typing import List, Protocol, Tuple, runtime_checkable

from playwright.sync_api import BrowserContext, Page

from hh_auto_apply.domain.entities import ApplyResult


@runtime_checkable
class JobBoardClient(Protocol):
    """Контракт, который обязана реализовать каждая площадка.

    Атрибут ``platform`` используется для разделения записей в базе
    "уже видел" (чтобы ID вакансий hh и LinkedIn не пересекались).
    """

    platform: str

    def ensure_logged_in(self, page: Page) -> None:
        """Гарантирует, что пользователь авторизован (иначе просит войти вручную)."""
        ...

    def build_search_url(self, page_num: int = 0) -> str:
        """Строит URL страницы поиска для указанной страницы пагинации."""
        ...

    def list_vacancies_with_titles(self, page: Page) -> List[Tuple[str, str]]:
        """Возвращает список пар (url вакансии, название) с текущей страницы поиска."""
        ...

    def apply_to_vacancy(
        self, context: BrowserContext, url: str, cover_text: str
    ) -> Tuple[ApplyResult, str]:
        """Открывает вакансию и пытается откликнуться. Возвращает (результат, название)."""
        ...

    def extract_job_id(self, url: str) -> str:
        """Извлекает стабильный ID вакансии из URL (для базы "уже видел")."""
        ...
