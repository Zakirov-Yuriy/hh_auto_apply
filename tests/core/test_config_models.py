"""Тесты разбора AI_MODEL: одна модель или список через запятую."""

from __future__ import annotations

import pytest

from hh_auto_apply.core.config import DEFAULT_AI_MODELS, Config, parse_model_list


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", []),
        ("a/b:free", ["a/b:free"]),
        (" a/b:free , c/d:free ", ["a/b:free", "c/d:free"]),
        ('"a/b:free","a/b:free"', ["a/b:free"]),
    ],
)
def test_parse_model_list(raw, expected):
    assert parse_model_list(raw) == expected


@pytest.fixture
def no_dotenv(monkeypatch):
    """Не читать .env проекта, иначе тест зависит от локальных настроек."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)


def test_from_env_uses_default_chain_when_unset(monkeypatch, no_dotenv):
    monkeypatch.delenv("AI_MODEL", raising=False)
    cfg = Config.from_env()
    assert cfg.ai_models == list(DEFAULT_AI_MODELS)
    assert cfg.ai_model == DEFAULT_AI_MODELS[0]


def test_from_env_parses_comma_separated_models(monkeypatch, no_dotenv):
    monkeypatch.setenv("AI_MODEL", "x/one:free, y/two:free")
    cfg = Config.from_env()
    assert cfg.ai_models == ["x/one:free", "y/two:free"]
    assert cfg.ai_model == "x/one:free"
