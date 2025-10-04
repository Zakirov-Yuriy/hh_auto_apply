import pytest

from hh_auto_apply.utils import extract_vacancy_id


@pytest.mark.parametrize(
    "url, expected_id",
    [
        ("https://hh.ru/vacancy/12345678", "12345678"),
        ("https://spb.hh.ru/vacancy/87654321?query=python", "87654321"),
        ("https://hh.ru/vacancy/11223344?from=what&uid=whatever", "11223344"),
        ("https://some.other.domain/vacancy/99999", "99999"),
        # Тест на случай, если регулярное выражение не сработает
        ("https://hh.ru/some/path/5554433", "5554433"),
    ],
)
def test_extract_vacancy_id(url, expected_id):
    assert extract_vacancy_id(url) == expected_id
