"""Тесты учёта исхода отклика в App._record_result.

App собирается без браузера и без SQLite: подставляем фейковый репозиторий
и отключаем запись CSV.
"""

from __future__ import annotations

import pytest

from hh_auto_apply.application.run_session import App
from hh_auto_apply.domain.entities import ApplyResult, Stats


class FakeRepo:
    def __init__(self):
        self.seen: list[str] = []

    def mark_seen(self, vac_id: str) -> None:
        self.seen.append(vac_id)


class FakeAI:
    def __init__(self, stopped_reason=None):
        self.stopped_reason = stopped_reason


class FakeClient:
    platform = "hh"

    def __init__(self, ai=None):
        self.ai = ai


class FakeCfg:
    use_ai_cover_letter = True


def make_app(ai=None) -> App:
    app = App.__new__(App)
    app.cfg = FakeCfg()
    app.dry_run = False
    app.repo = FakeRepo()
    app.client = FakeClient(ai)
    app.failed_vacancies_csv = "unused.csv"
    app._append_vacancy_to_csv = lambda *a, **k: None
    app._append_failed_vacancy_to_csv = lambda *a, **k: None
    return app


@pytest.mark.parametrize(
    "result, seen, counter, applied",
    [
        (ApplyResult.SUCCESS, True, "applies_done", True),
        (ApplyResult.SKIPPED_ALREADY_APPLIED, True, "skipped_already", False),
        (ApplyResult.SKIPPED_EXTERNAL, True, "skipped_external", False),
        (ApplyResult.SKIPPED_FORM_INCOMPLETE, True, "skipped_form", False),
        (ApplyResult.ERROR, True, "errors", False),
        (ApplyResult.SKIPPED_AI_UNAVAILABLE, False, "skipped_ai", False),
    ],
)
def test_record_result(result, seen, counter, applied):
    app = make_app()
    stats = Stats()

    applied_now = app._record_result(result, "hh:1", "Вакансия", "https://hh.ru/vacancy/1", stats)
    assert applied_now is applied
    assert (app.repo.seen == ["hh:1"]) is seen
    assert getattr(stats, counter) == 1


def test_ai_stopped_only_when_client_reports_reason():
    assert not make_app(FakeAI())._ai_stopped()
    assert make_app(FakeAI("дневной лимит"))._ai_stopped()
    assert not make_app(None)._ai_stopped()
