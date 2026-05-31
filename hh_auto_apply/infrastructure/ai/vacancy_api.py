"""HH.ru API клиент для получения структурированных данных вакансии.

Используется для генерации сопроводительного письма с правильными ATS-тегами.
Преимущество перед скрапингом DOM: HH API возвращает поле `key_skills` отдельным
списком, который HH сам использует для матчинга кандидатов. Эти точные теги
должны попадать в письмо дословно.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Optional

import requests
from loguru import logger


HH_API_URL = "https://api.hh.ru/vacancies/{vacancy_id}"


def _strip_html(html: str) -> str:
    """Удаляет HTML-теги и декодирует HTML-сущности, сохраняя структуру списков."""
    if not html:
        return ""
    # Сохраняем структуру списков и параграфов
    text = re.sub(r"</(li|p|h\d|div|br)\s*>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    # Удаляем все остальные теги
    text = re.sub(r"<[^>]+>", "", text)
    # Декодируем HTML-сущности
    text = unescape(text)
    # Чистим лишние пробелы и переносы
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_vacancy(
    vacancy_id: str,
    user_agent: str = "ZakirovCoverLetter/1.0 (zak.yuri@yandex.ru)",
    timeout: int = 10,
) -> Optional[dict]:
    """Получает данные вакансии с HH.ru через официальное API.

    Args:
        vacancy_id: ID вакансии (например, "133398355").
        user_agent: User-Agent, HH требует формат "Имя/Версия (email)".
        timeout: Таймаут запроса в секундах.

    Returns:
        Словарь со структурированными данными или None при ошибке.
        Структура: title, company, city, experience, employment, schedule,
        salary, key_skills (list), professional_roles (list), description,
        url, contacts.
    """
    url = HH_API_URL.format(vacancy_id=vacancy_id)
    headers = {"User-Agent": user_agent}

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        body = e.response.text[:200] if e.response is not None else ""
        logger.warning(
            f"HH API вернул {status} для vacancy_id={vacancy_id}: {body}"
        )
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Ошибка запроса к HH API для vacancy_id={vacancy_id}: {e}")
        return None
    except ValueError as e:
        logger.warning(f"HH API вернул не-JSON для vacancy_id={vacancy_id}: {e}")
        return None

    return {
        "title": data.get("name", ""),
        "company": (data.get("employer") or {}).get("name", ""),
        "city": (data.get("area") or {}).get("name", ""),
        "experience": (data.get("experience") or {}).get("name", ""),
        "employment": (data.get("employment") or {}).get("name", ""),
        "schedule": (data.get("schedule") or {}).get("name", ""),
        "salary": data.get("salary"),
        "key_skills": [s["name"] for s in (data.get("key_skills") or [])],
        "professional_roles": [
            r["name"] for r in (data.get("professional_roles") or [])
        ],
        "description": _strip_html(data.get("description", "")),
        "url": data.get("alternate_url", ""),
        "contacts": data.get("contacts"),
    }


def format_for_prompt(vacancy: dict) -> str:
    """Форматирует данные вакансии для подстановки в плейсхолдер {job_description}.

    Ключевые навыки выносятся отдельным блоком с пометкой, что это
    точные ATS-теги HH и их формулировки должны попасть в письмо дословно.
    """
    parts = []

    if vacancy.get("title"):
        parts.append(f"НАЗВАНИЕ РОЛИ: {vacancy['title']}")

    if vacancy.get("company"):
        parts.append(f"КОМПАНИЯ: {vacancy['company']}")

    if vacancy.get("city"):
        parts.append(f"ГОРОД: {vacancy['city']}")

    if vacancy.get("experience"):
        parts.append(f"ОПЫТ: {vacancy['experience']}")

    if vacancy.get("professional_roles"):
        parts.append(
            "ПРОФЕССИОНАЛЬНАЯ РОЛЬ: "
            + ", ".join(vacancy["professional_roles"])
        )

    # Контактное лицо
    contacts = vacancy.get("contacts")
    if contacts and isinstance(contacts, dict):
        contact_name = contacts.get("name")
        if contact_name:
            parts.append(f"КОНТАКТНОЕ ЛИЦО: {contact_name}")

    # Ключевые навыки от HH - критично для ATS
    if vacancy.get("key_skills"):
        skills_block = "КЛЮЧЕВЫЕ НАВЫКИ (key_skills от HH, используй эти формулировки в письме дословно):\n"
        skills_block += "\n".join(f"- {skill}" for skill in vacancy["key_skills"])
        parts.append(skills_block)

    if vacancy.get("description"):
        parts.append("ПОЛНОЕ ОПИСАНИЕ:\n" + vacancy["description"])

    return "\n\n".join(parts)


def build_job_description(
    vacancy_id: str,
    user_agent: str = "ZakirovCoverLetter/1.0 (zak.yuri@yandex.ru)",
) -> Optional[str]:
    """Удобная обёртка: по vacancy_id вернёт готовый текст для подстановки в промт.

    Returns:
        Строка для {job_description} или None если HH API недоступен.
    """
    vacancy = fetch_vacancy(vacancy_id, user_agent=user_agent)
    if not vacancy:
        return None
    return format_for_prompt(vacancy)
