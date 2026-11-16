"""Капча: бот ждёт ручного ввода и продолжает, когда окно исчезло."""

from __future__ import annotations

import pytest

from hh_auto_apply.infrastructure.browser import hh_client as mod
from hh_auto_apply.infrastructure.browser.hh_client import CaptchaNotSolved, HHClient
from hh_auto_apply.infrastructure.browser.selectors import Selectors

CAPTCHA_INPUT = Selectors.CAPTCHA_MARKERS[0]


class FakeLocator:
    def __init__(self, visible: bool):
        self.visible = visible

    def count(self):
        return 1 if self.visible else 0

    @property
    def first(self):
        return self

    def is_visible(self):
        return self.visible


class FakePage:
    """Капча видна первые `solve_after` проверок, потом исчезает."""

    def __init__(self, solve_after: int | None):
        self.solve_after = solve_after
        self.checks = 0
        self.url = "https://hh.ru/vacancy/1"
        self.waited_ms = 0
        self.fronted = False

    def locator(self, selector):
        if selector != CAPTCHA_INPUT:
            return FakeLocator(False)
        self.checks += 1
        visible = self.solve_after is None or self.checks <= self.solve_after
        return FakeLocator(visible)

    def wait_for_timeout(self, ms):
        self.waited_ms += ms

    def bring_to_front(self):
        self.fronted = True

    def screenshot(self, **kwargs):
        pass


def make_client(mock_config) -> HHClient:
    mock_config.openrouter_api_keys = []
    mock_config.captcha_wait_minutes = getattr(mock_config, "captcha_wait_minutes", 0) or 0
    mock_config.captcha_beep_every = 20
    client = HHClient(mock_config)
    client.make_shot = lambda page, tag: None
    return client


def test_no_captcha_returns_false(mock_config, monkeypatch):
    client = make_client(mock_config)
    monkeypatch.setattr(HHClient, "_beep", staticmethod(lambda: None))
    page = FakePage(solve_after=0)
    assert client.wait_for_manual_captcha(page) is False
    assert page.fronted is False


def test_waits_until_captcha_solved(mock_config, monkeypatch):
    beeps = []
    monkeypatch.setattr(HHClient, "_beep", staticmethod(lambda: beeps.append(1)))
    client = make_client(mock_config)
    page = FakePage(solve_after=4)
    assert client.wait_for_manual_captcha(page) is True
    assert page.fronted is True
    assert beeps, "должен прозвучать сигнал"


def test_timeout_raises(mock_config, monkeypatch):
    monkeypatch.setattr(HHClient, "_beep", staticmethod(lambda: None))
    mock_config.captcha_wait_minutes = 1
    client = make_client(mock_config)
    clock = iter(range(0, 100000, 10))  # каждая проверка «прошло 10 секунд»
    monkeypatch.setattr(mod.time, "monotonic", lambda: next(clock))
    with pytest.raises(CaptchaNotSolved):
        client.wait_for_manual_captcha(FakePage(solve_after=None))
