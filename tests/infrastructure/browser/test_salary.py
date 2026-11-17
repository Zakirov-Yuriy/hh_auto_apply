"""Зарплатные ожидания берутся из настроек, а не из зашитых 130 000 (17.11.2026)."""

from __future__ import annotations

from hh_auto_apply.infrastructure.browser.hh_client import HHClient


def make(mock_config, low, high):
    mock_config.openrouter_api_keys = []
    mock_config.salary_expectation = low
    mock_config.salary_max = high
    return HHClient(mock_config)


def test_range(mock_config):
    c = make(mock_config, "230000", "250000")
    assert c.salary_text() == "от 230 000 до 250 000 руб. на руки"
    assert c.salary_number() == "230000"


def test_only_lower(mock_config):
    assert make(mock_config, "230 000", "").salary_text() == "от 230 000 руб. на руки"


def test_free_phrase(mock_config):
    c = make(mock_config, "по договорённости", "")
    assert c.salary_text() == "по договорённости"
    assert c.salary_number() == ""


def test_salary_question_uses_range(mock_config):
    c = make(mock_config, "230000", "250000")
    c.ai = object()  # до нейросети дело дойти не должно
    out = c._generate_answers_for_custom_questions(
        [{"question": "Ваши зарплатные ожидания?", "type": "textarea", "field_name": "task_1"}],
        {"salary": c.salary_text()}, "PHP разработчик",
    )
    assert out[0]["answer"] == "от 230 000 до 250 000 руб. на руки"


def test_no_130k_anywhere(mock_config):
    c = make(mock_config, "230000", "250000")
    assert "130" not in c._salary_facts()


def test_resume_salary_wins(mock_config):
    c = make(mock_config, "230000", "250000")
    c.resume_salary = c._salary_from_text("fullstack developer (flutter php laravel) 250 000 ₽")
    assert c.resume_salary == "250000"
    assert c.salary_text() == "от 250 000 руб. на руки"
    assert c.salary_number() == "250000"


def test_salary_from_text_nbsp(mock_config):
    c = make(mock_config, "230000", "")
    assert c._salary_from_text("Senior Backend 230 000 ₽") == "230000"
    assert c._salary_from_text("Senior Flutter developer") == ""
