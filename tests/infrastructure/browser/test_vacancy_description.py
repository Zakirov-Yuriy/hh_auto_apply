"""Описание вакансии со страницы собирается в формат HH API (шапка + текст)."""

from __future__ import annotations

from hh_auto_apply.infrastructure.browser.hh_client import HHClient
from hh_auto_apply.infrastructure.browser.selectors import Selectors


class FakeLocator:
    def __init__(self, texts):
        self.texts = texts

    def count(self):
        return len(self.texts)

    @property
    def first(self):
        return FakeLocator(self.texts[:1])

    def nth(self, i):
        return FakeLocator([self.texts[i]])

    def inner_text(self):
        return self.texts[0] if self.texts else ""

    def wait_for(self, state="visible", timeout=0):
        if not self.texts:
            raise TimeoutError("not visible")


class FakePage:
    def __init__(self, data):
        self.data = data

    def locator(self, selector):
        return FakeLocator(self.data.get(selector, []))


def make_client(mock_config) -> HHClient:
    mock_config.openrouter_api_keys = []
    return HHClient(mock_config)


def test_description_includes_header_and_skills(mock_config, tmp_path):
    mock_config.screenshots_dir = str(tmp_path)
    page = FakePage({
        Selectors.VACANCY_TITLE_QA: ["PHP/Laravel-разработчик (Middle+/Senior)"],
        Selectors.VACANCY_COMPANY_QA: ["ООО Медтехсофт"],
        Selectors.VACANCY_EXPERIENCE_QA: ["3–6 лет"],
        Selectors.VACANCY_KEY_SKILL_QA: ["• PHP 8.4 • Laravel 12 • PostgreSQL", "Redis"],
        Selectors.VACANCY_DESCRIPTION_QA: [
            "Обязанности: писать код на Laravel и чинить баги в проде."
        ],
    })

    text = make_client(mock_config)._get_vacancy_description(page)

    assert text.startswith("НАЗВАНИЕ РОЛИ: PHP/Laravel-разработчик (Middle+/Senior)")
    assert "КОМПАНИЯ: ООО Медтехсофт" in text
    assert "ОПЫТ: 3–6 лет" in text
    assert "- PHP 8.4\n- Laravel 12\n- PostgreSQL\n- Redis" in text
    assert text.endswith(
        "ПОЛНОЕ ОПИСАНИЕ:\nОбязанности: писать код на Laravel и чинить баги в проде."
    )


def test_description_without_header_still_works(mock_config, tmp_path):
    mock_config.screenshots_dir = str(tmp_path)
    page = FakePage({
        Selectors.VACANCY_DESCRIPTION_QA: [
            "Текст описания вакансии длиннее пятидесяти символов, чтобы пройти проверку."
        ]
    })

    text = make_client(mock_config)._get_vacancy_description(page)

    assert text.startswith("ПОЛНОЕ ОПИСАНИЕ:\nТекст описания")
    assert "НАЗВАНИЕ РОЛИ" not in text


def test_no_description_returns_empty(mock_config, tmp_path):
    mock_config.screenshots_dir = str(tmp_path)
    assert make_client(mock_config)._get_vacancy_description(FakePage({})) == ""
