"""Тесты OpenRouterClient: ротация ключей и цепочка запасных моделей.

Сеть подменяется фейковым post, пауза подменяется записью в список.
"""

from __future__ import annotations

import json
from typing import List

import pytest
import requests

from hh_auto_apply.infrastructure.ai.openrouter import (
    APIKeyRotator,
    OpenRouterClient,
    Verdict,
    classify_rate_limit,
    classify_response,
)


class FakeResponse:
    """Минимум от requests.Response, который читает клиент."""

    def __init__(self, status: int, body: dict | str):
        self.status_code = status
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


def ok(text: str, finish: str = "stop") -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"content": text}, "finish_reason": finish}]})


def err(status: int, message: str, raw: str = "") -> FakeResponse:
    meta = {"raw": raw} if raw else {}
    return FakeResponse(status, {"error": {"code": status, "message": message, "metadata": meta}})


UPSTREAM_429 = err(
    429,
    "Provider returned error",
    "google/gemma-4-31b-it:free is temporarily rate-limited upstream. Please retry shortly",
)
DAILY_429 = err(429, "Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000")
MINUTE_429 = err(429, "Rate limit exceeded: free-models-per-min")


class FakePost:
    """Отдаёт ответы по очереди и запоминает, с какой моделью и ключом звали."""

    def __init__(self, responses: List[FakeResponse | Exception]):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url, headers, json, timeout):  # noqa: A002 (сигнатура requests.post)
        self.calls.append((json["model"], headers["Authorization"].removeprefix("Bearer ")))
        if not self.responses:
            raise AssertionError("лишний запрос к API")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(post: FakePost, keys=("k1",), models=("m1", "m2")):
    sleeps: list[float] = []
    client = OpenRouterClient(
        list(keys), list(models), retry_pause=1.0, sleep=sleeps.append, post=post
    )
    return client, sleeps


# ---------- APIKeyRotator ----------


def test_rotator_requires_keys():
    with pytest.raises(ValueError):
        APIKeyRotator([])


def test_rotator_single_key_cannot_rotate():
    rotator = APIKeyRotator(["only"])
    assert rotator.get_current_key() == "only"
    assert not rotator.has_multiple_keys()
    with pytest.raises(ValueError):
        rotator.rotate_to_next()


def test_rotator_cycles_keys():
    rotator = APIKeyRotator(["a", "b"])
    assert rotator.rotate_to_next() == "b"
    assert rotator.rotate_to_next() == "a"


# ---------- классификация ----------


@pytest.mark.parametrize(
    "message, verdict",
    [
        ("Rate limit exceeded: free-models-per-day", Verdict.NEXT_KEY),
        ("Rate limit exceeded: free-models-per-min", Verdict.RETRY_SAME),
        ("Provider returned error | raw=temporarily rate-limited upstream", Verdict.NEXT_MODEL),
        ("something unknown", Verdict.RETRY_SAME),
    ],
)
def test_classify_rate_limit(message, verdict):
    assert classify_rate_limit(message) == verdict


@pytest.mark.parametrize(
    "response, verdict",
    [
        (ok("письмо"), Verdict.DONE),
        (ok("", finish="length"), Verdict.NEXT_MODEL),
        (UPSTREAM_429, Verdict.NEXT_MODEL),
        (DAILY_429, Verdict.NEXT_KEY),
        (MINUTE_429, Verdict.RETRY_SAME),
        (err(401, "No auth credentials found"), Verdict.NEXT_KEY),
        (err(402, "Insufficient credits"), Verdict.NEXT_MODEL),
        (err(404, "No endpoints found that support your data policy"), Verdict.STOP),
        (err(404, "No endpoints found for model"), Verdict.NEXT_MODEL),
        (err(403, "only available on agentic harnesses"), Verdict.NEXT_MODEL),
        (err(400, "reasoning not supported"), Verdict.NEXT_MODEL),
        (err(502, "Bad gateway"), Verdict.RETRY_SAME),
        (FakeResponse(200, "<html>oops</html>"), Verdict.RETRY_SAME),
        (
            FakeResponse(200, {"error": {"code": 429, "message": "free-models-per-min"}}),
            Verdict.RETRY_SAME,
        ),
    ],
)
def test_classify_response(response, verdict):
    assert classify_response(response).verdict == verdict


# ---------- OpenRouterClient.complete ----------


def test_first_model_answers():
    post = FakePost([ok("  Здравствуйте!  ")])
    client, sleeps = make_client(post)

    assert client.complete("p", max_tokens=10, temperature=0.1) == "Здравствуйте!"
    assert post.calls == [("m1", "k1")]
    assert sleeps == []


def test_upstream_limit_switches_model_without_waiting():
    post = FakePost([UPSTREAM_429, ok("от второй")])
    client, sleeps = make_client(post)

    assert client.complete("p", max_tokens=10, temperature=0.1) == "от второй"
    assert [m for m, _ in post.calls] == ["m1", "m2"]
    assert sleeps == []


def test_empty_answer_switches_model():
    post = FakePost([ok("", finish="length"), ok("текст")])
    client, _ = make_client(post)

    assert client.complete("p", max_tokens=10, temperature=0.1) == "текст"
    assert [m for m, _ in post.calls] == ["m1", "m2"]


def test_minute_limit_waits_and_retries_same_model():
    post = FakePost([MINUTE_429, ok("после паузы")])
    client, sleeps = make_client(post)

    assert client.complete("p", max_tokens=10, temperature=0.1) == "после паузы"
    assert [m for m, _ in post.calls] == ["m1", "m1"]
    assert sleeps == [1.0]


def test_network_error_retries_then_falls_to_next_model():
    post = FakePost(
        [requests.exceptions.ConnectionError("down")] * 3 + [ok("запасная")]
    )
    client, sleeps = make_client(post)

    assert client.complete("p", max_tokens=10, temperature=0.1) == "запасная"
    assert [m for m, _ in post.calls] == ["m1", "m1", "m1", "m2"]
    assert len(sleeps) == 2  # после третьей неудачи не ждём, сразу следующая модель


def test_daily_limit_rotates_key_and_keeps_model():
    post = FakePost([DAILY_429, ok("вторым ключом")])
    client, sleeps = make_client(post, keys=("k1", "k2"))

    assert client.complete("p", max_tokens=10, temperature=0.1) == "вторым ключом"
    assert post.calls == [("m1", "k1"), ("m1", "k2")]
    assert sleeps == []


def test_daily_limit_with_single_key_stops_everything():
    post = FakePost([DAILY_429])
    client, _ = make_client(post, keys=("k1",), models=("m1", "m2", "m3"))

    assert client.complete("p", max_tokens=10, temperature=0.1) is None
    # Дневной лимит общий на аккаунт, перебирать модели бессмысленно.
    assert post.calls == [("m1", "k1")]
    assert client.stopped_reason

    # Следующая вакансия: в сеть не ходим, сразу None.
    assert client.complete("p", max_tokens=10, temperature=0.1) is None
    assert len(post.calls) == 1


def test_bad_key_rotates_and_next_key_stays_for_later_calls():
    post = FakePost([err(401, "bad key"), ok("ок"), ok("ещё")])
    client, _ = make_client(post, keys=("dead", "live"))

    assert client.complete("p", max_tokens=10, temperature=0.1) == "ок"
    assert client.complete("p", max_tokens=10, temperature=0.1) == "ещё"
    assert [k for _, k in post.calls] == ["dead", "live", "live"]


def test_data_policy_error_stops_without_trying_other_models():
    post = FakePost([err(404, "No endpoints found that support your data policy")])
    client, _ = make_client(post, models=("m1", "m2"))

    assert client.complete("p", max_tokens=10, temperature=0.1) is None
    assert len(post.calls) == 1


def test_all_models_fail_returns_none():
    post = FakePost([err(402, "paid now"), UPSTREAM_429])
    client, _ = make_client(post)

    assert client.complete("p", max_tokens=10, temperature=0.1) is None
    assert [m for m, _ in post.calls] == ["m1", "m2"]


def test_models_are_trimmed_and_empty_rejected():
    client = OpenRouterClient(["k"], [" a ", "b"], post=FakePost([]))
    assert client.models == ["a", "b"]
    with pytest.raises(ValueError):
        OpenRouterClient(["k"], [], post=FakePost([]))


def test_request_payload_disables_reasoning():
    captured = {}

    def post(url, headers, json, timeout):  # noqa: A002
        captured.update(json)
        return ok("x")

    client = OpenRouterClient(["k"], ["m"], post=post)
    client.complete("промпт", max_tokens=123, temperature=0.5)

    assert captured["model"] == "m"
    assert captured["max_tokens"] == 123
    assert captured["temperature"] == 0.5
    assert captured["reasoning"] == {"enabled": False, "exclude": True}
    assert captured["messages"] == [{"role": "user", "content": "промпт"}]


# ---------- память о мёртвых моделях и ключах, preflight, отчёт ----------


def test_retired_model_is_skipped_on_later_calls():
    post = FakePost([err(402, "paid now"), ok("раз"), ok("два")])
    client, _ = make_client(post)

    assert client.complete("p", max_tokens=10, temperature=0.1) == "раз"
    assert client.complete("p", max_tokens=10, temperature=0.1) == "два"
    # m1 выбыла после 402 и во второй раз не дёргалась.
    assert [m for m, _ in post.calls] == ["m1", "m2", "m2"]
    assert "m1" in client.dead_models


def test_all_models_retired_stops_with_reason():
    post = FakePost([err(404, "This model is unavailable for free"), err(402, "paid")])
    client, _ = make_client(post)

    assert client.complete("p", max_tokens=10, temperature=0.1) is None
    assert client.stopped_reason and "выбыли" in client.stopped_reason
    # Следующий вызов в сеть не ходит.
    assert client.complete("p", max_tokens=10, temperature=0.1) is None
    assert len(post.calls) == 2


def test_dead_key_is_not_reused_across_models():
    # Ключ k1 не принят. При переходе на вторую модель бот не должен снова
    # пробовать k1.
    post = FakePost([err(401, "bad"), UPSTREAM_429, ok("ок")])
    client, _ = make_client(post, keys=("k1", "k2"))

    assert client.complete("p", max_tokens=10, temperature=0.1) == "ок"
    assert post.calls == [("m1", "k1"), ("m1", "k2"), ("m2", "k2")]


def key_response(remaining: int | None, status: int = 200) -> FakeResponse:
    if status != 200:
        return FakeResponse(status, {"error": {"code": status, "message": "no"}})
    daily = {"used": 50 - remaining, "limit": 50, "remaining": remaining} if remaining is not None else {}
    return FakeResponse(200, {"data": {"label": "x", "free_model_daily_requests": daily}})


def catalog_response(*entries: tuple[str, str]) -> FakeResponse:
    data = [{"id": mid, "pricing": {"prompt": price, "completion": price}} for mid, price in entries]
    return FakeResponse(200, {"data": data})


class FakeGet:
    def __init__(self, by_url: dict):
        self.by_url = by_url

    def __call__(self, url, headers=None, timeout=None):
        item = self.by_url[url]
        if isinstance(item, list):
            return item.pop(0)
        return item


def test_preflight_reports_keys_and_models():
    from hh_auto_apply.infrastructure.ai.openrouter import KEY_URL, MODELS_URL

    get = FakeGet({
        KEY_URL: [key_response(42), key_response(None, status=401), key_response(0)],
        MODELS_URL: catalog_response(("good:free", "0"), ("qwen/x", "0.000002"), ("paid:free", "0.1")),
    })
    client = OpenRouterClient(
        ["k1", "k2", "k3"], ["good:free", "qwen/x:free", "paid:free", "gone:free"],
        post=FakePost([]), get=get,
    )
    report = client.preflight()

    assert report.ok
    assert [k.ok for k in report.keys] == [True, False, True]
    assert report.keys[2].daily_remaining == 0
    assert report.daily_remaining_total == 42
    assert report.available_models == ["good:free"]
    assert "платная qwen/x" in report.missing_models["qwen/x:free"]
    assert report.missing_models["paid:free"] == "модель стала платной"
    assert report.missing_models["gone:free"] == "модели нет в каталоге OpenRouter"
    # Мёртвые ключи и модели запомнены, живой ключ один.
    assert client.key_rotator.alive_keys() == ["k1"]
    assert set(client.dead_models) == {"qwen/x:free", "paid:free", "gone:free"}


def test_preflight_fails_when_no_free_model_left():
    from hh_auto_apply.infrastructure.ai.openrouter import KEY_URL, MODELS_URL

    get = FakeGet({KEY_URL: key_response(50), MODELS_URL: catalog_response(("other:free", "0"))})
    client = OpenRouterClient(["k1"], ["gone:free"], post=FakePost([]), get=get)

    assert not client.preflight().ok


def test_preflight_fails_when_daily_limit_exhausted_everywhere():
    from hh_auto_apply.infrastructure.ai.openrouter import KEY_URL, MODELS_URL

    get = FakeGet({KEY_URL: [key_response(0), key_response(0)], MODELS_URL: catalog_response(("m:free", "0"))})
    client = OpenRouterClient(["k1", "k2"], ["m:free"], post=FakePost([]), get=get)

    report = client.preflight()
    assert not report.ok
    assert report.daily_remaining_total == 0


def test_preflight_without_catalog_still_ok_on_live_key():
    from hh_auto_apply.infrastructure.ai.openrouter import KEY_URL, MODELS_URL

    get = FakeGet({KEY_URL: key_response(10), MODELS_URL: FakeResponse(503, "down")})
    client = OpenRouterClient(["k1"], ["m:free"], post=FakePost([]), get=get)

    report = client.preflight()
    assert report.ok
    assert not report.catalog_checked


def test_report_lines_mention_models_keys_and_stop():
    post = FakePost([ok("a"), err(402, "paid"), ok("b")])
    client, _ = make_client(post, models=("m1", "m2"))
    client.complete("p", max_tokens=10, temperature=0.1)
    # Вторая модель выбывает, первая отвечает дважды? Нет: m1 ответила, затем
    # во втором вызове m1 вернула 402 и выбыла, ответила m2.
    client.complete("p", max_tokens=10, temperature=0.1)

    lines = "\n".join(client.report_lines())
    assert "успешных): 2" in lines
    assert "m1: 1" in lines and "m2: 1" in lines
    assert "Модель выбыла: m1" in lines
