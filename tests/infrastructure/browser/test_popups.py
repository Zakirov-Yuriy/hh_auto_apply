"""Всплывающие окна: бот заполняет и подтверждает любое окно, кроме капчи и формы отклика.

Тесты гоняют настоящий Chromium на локальной HTML-странице.
"""

from __future__ import annotations

import pytest

pw = pytest.importorskip("playwright.sync_api")

from hh_auto_apply.infrastructure.browser.hh_client import HHClient  # noqa: E402

RESULT_JS = """
<script>
  window.result = {};
  function done(id, data) { window.result[id] = data; document.getElementById(id).remove(); }
</script>
"""


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # pragma: no cover
            pytest.skip(f"Chromium недоступен: {e}")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    pg = browser.new_page()
    yield pg
    pg.close()


@pytest.fixture
def client(mock_config, monkeypatch):
    mock_config.openrouter_api_keys = []
    mock_config.min_sleep = 0
    mock_config.max_sleep = 0
    mock_config.hh_city = "Москва"
    c = HHClient(mock_config)
    c.make_shot = lambda page, tag: None
    asked = []

    def fake_ai(questions, resume_context, vacancy_title):
        out = []
        for q in questions:
            asked.append(q)
            q = dict(q)
            if q["type"] == "radio":
                q["answer"] = q["options"][1]["value"]
            else:
                q["answer"] = "Ответ нейросети"
            out.append(q)
        return out

    monkeypatch.setattr(c, "_generate_answers_for_custom_questions", fake_ai)
    c.asked = asked
    return c


def test_city_popup(page, client):
    page.set_content(RESULT_JS + """
    <div id="d" role="dialog">
      <h2>Выберите город</h2>
      <input placeholder="Город" id="city">
      <ul role="listbox" id="lb"></ul>
      <button onclick="done('d', document.getElementById('city').value)">Выбрать</button>
      <button onclick="done('d', 'cancel')">Отмена</button>
    </div>
    <script>
      document.getElementById('city').addEventListener('input', e => {
        document.getElementById('lb').innerHTML =
          '<li role="option" onclick="document.getElementById(\\'city\\').value=\\'Москва, Россия\\'">Москва, Россия</li>';
      });
    </script>""")
    assert client.handle_popups(page) == 1
    assert page.evaluate("window.result.d") == "Москва, Россия"


def test_text_popup_filled_by_ai(page, client):
    page.set_content(RESULT_JS + """
    <div id="d" role="dialog">
      <h2>Уточните информацию</h2>
      <label for="t">Почему вы хотите у нас работать?</label>
      <textarea id="t"></textarea>
      <button onclick="done('d', document.getElementById('t').value)">Отправить</button>
    </div>""")
    assert client.handle_popups(page, "Python разработчик") == 1
    assert page.evaluate("window.result.d") == "Ответ нейросети"
    assert "Почему вы хотите" in client.asked[0]["question"]


def test_radio_select_and_checkbox(page, client):
    page.set_content(RESULT_JS + """
    <div id="d" role="dialog">
      <h2>Готовы к переезду?</h2>
      <label><input type="radio" name="r" value="no">Нет</label>
      <label><input type="radio" name="r" value="yes">Да</label>
      <select id="s"><option value="">—</option><option value="1">Санкт-Петербург</option><option value="2">Москва</option></select>
      <label><input type="checkbox" id="c" required>Согласен</label>
      <button onclick="done('d', [document.querySelector('[name=r]:checked').value,
        document.getElementById('s').value, document.getElementById('c').checked])">Продолжить</button>
    </div>""")
    assert client.handle_popups(page) == 1
    assert page.evaluate("window.result.d") == ["yes", "2", True]


def test_foreign_country_popup(page, client):
    page.set_content(RESULT_JS + """
    <div id="d" role="dialog">
      <p>Вакансия в другой стране</p>
      <button onclick="done('d', 'cancel')">Отменить</button>
      <button onclick="done('d', 'ok')">Все равно откликнуться</button>
    </div>""")
    assert client.handle_popups(page) == 1
    assert page.evaluate("window.result.d") == "ok"


def test_chain_of_popups(page, client):
    page.set_content(RESULT_JS + """
    <div id="a" role="dialog"><p>Первое</p>
      <button onclick="done('a', 1); document.getElementById('b').hidden = false">Понятно</button></div>
    <div id="b" role="dialog" hidden><p>Второе</p>
      <button onclick="done('b', 2)">Продолжить</button></div>""")
    assert client.handle_popups(page) == 2
    assert page.evaluate("window.result") == {"a": 1, "b": 2}


def test_response_form_is_left_to_main_flow(page, client):
    page.set_content("""
    <div role="dialog">
      <textarea data-qa="vacancy-response-letter-input"></textarea>
      <button data-qa="vacancy-response-submit-button">Отправить</button>
    </div>""")
    assert client.handle_popups(page) == 0
    assert page.locator("textarea").input_value() == ""


def test_captcha_is_never_typed_by_bot(page, client, monkeypatch):
    page.set_content("""
    <div role="dialog" id="cap">
      <img src="/captcha.png">
      <input placeholder="Текст с картинки" id="ci">
      <button>Отправить</button>
    </div>""")
    calls = []

    def human_solves(pg):
        if pg.locator("#cap").count():
            calls.append(pg.locator("#ci").input_value())
            pg.evaluate("document.getElementById('cap').remove()")
            return True
        return False

    monkeypatch.setattr(client, "wait_for_manual_captcha", human_solves)
    assert client.handle_popups(page) == 1
    assert calls == [""], "поле капчи бот заполнять не должен"
    assert client.asked == []


def test_stuck_popup_does_not_loop(page, client):
    page.set_content("""
    <div role="dialog"><p>Окно не закрывается</p><button>Понятно</button></div>""")
    assert client.handle_popups(page) == 1


def test_salary_number_field_gets_lower_bound(page, client):
    client.cfg.salary_expectation = "230000"
    client.cfg.salary_max = "250000"
    page.set_content(RESULT_JS + """
    <div id="d" role="dialog">
      <h2>Зарплатные ожидания</h2>
      <input type="number" aria-label="Сумма, руб.">
      <button onclick="done('d', document.querySelector('input').value)">Отправить</button>
    </div>""")
    assert client.handle_popups(page) == 1
    assert page.evaluate("window.result.d") == "230000"


def test_new_hh_response_form_is_not_touched(page, client):
    """Лог 17.11: «Всплывающее окно: «Откликнуться». В окне не нашлось кнопки»."""
    page.set_content("""
    <div role="dialog">
      <h2>Откликнуться</h2>
      <label><input type="radio" name="r" checked>Senior Backend Developer (PHP Laravel) 230 000 ₽</label>
      <label><input type="radio" name="r">Fullstack Developer (Flutter PHP Laravel) 250 000 ₽</label>
      <textarea id="t"></textarea>
    </div>""")
    assert client.handle_popups(page) == 0
    assert page.locator("#t").input_value() == ""
    assert client.asked == []
