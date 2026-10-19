"""Чистка текста, который вернула нейросеть.

Чистые функции без состояния и без сети, чтобы их можно было проверить
тестами отдельно от HTTP.
"""

from __future__ import annotations

import re


# Служебные токены, которые некоторые модели добавляют в текст.
_CHAT_TOKENS = ("<s>", "</s>", "[INST]", "[/INST]")

# Длинное и среднее тире. Промпты запрещают их в письме, но модели всё равно
# ставят (19.10.2026: Nemotron 3 Super и Ultra в каждом письме). Чинить в
# коде надёжнее, чем уговаривать модель.
_LONG_DASHES = re.compile(r"[—–]")

# Markdown-обёртка ```...```, в которую модели иногда заворачивают ответ.
_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def strip_chat_tokens(text: str) -> str:
    """Убирает служебные токены вроде <s> и [INST] и обрезает пробелы."""
    for token in _CHAT_TOKENS:
        text = text.replace(token, "")
    return text.strip()


def replace_long_dashes(text: str) -> str:
    """Меняет длинное и среднее тире на обычный дефис.

    Пробелы вокруг не трогаем: «слово — слово» становится «слово - слово»,
    как и просит промпт.
    """
    return _LONG_DASHES.sub("-", text)


def strip_code_fence(text: str) -> str:
    """Снимает обёртку ```json ... ```, если модель её добавила."""
    return _CODE_FENCE.sub("", text.strip()).strip()


def clean_letter(text: str) -> str:
    """Полная чистка сопроводительного письма: токены, обёртка, тире."""
    return replace_long_dashes(strip_code_fence(strip_chat_tokens(text)))
