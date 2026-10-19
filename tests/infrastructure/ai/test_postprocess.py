"""Тесты чистки текста от нейросети."""

from __future__ import annotations

import pytest

from hh_auto_apply.infrastructure.ai.postprocess import (
    clean_letter,
    replace_long_dashes,
    strip_chat_tokens,
    strip_code_fence,
)


def test_strip_chat_tokens():
    assert strip_chat_tokens("<s>[INST] текст [/INST]</s> ") == "текст"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Я — разработчик", "Я - разработчик"),
        ("2019–2023", "2019-2023"),
        ("без тире", "без тире"),
    ],
)
def test_replace_long_dashes(raw, expected):
    assert replace_long_dashes(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('```json\n{"value": "1"}\n```', '{"value": "1"}'),
        ('```\n{"values": []}```', '{"values": []}'),
        ('{"value": "2"}', '{"value": "2"}'),
    ],
)
def test_strip_code_fence(raw, expected):
    assert strip_code_fence(raw) == expected


def test_clean_letter_combines_everything():
    raw = "<s>```\nЗдравствуйте!\n\nСтек — PHP, Laravel.\n```</s>"
    assert clean_letter(raw) == "Здравствуйте!\n\nСтек - PHP, Laravel."
