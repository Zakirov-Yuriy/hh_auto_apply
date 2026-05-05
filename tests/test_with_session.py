#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Директный тест вакансии 132780378 с использованием сохранённой сессии браузера.
"""
import sys
import os

if sys.platform == "win32":
    os.system("chcp 65001 > nul")

from pathlib import Path
from playwright.sync_api import sync_playwright
from loguru import logger
from hh_auto_apply.core.config import Config
from hh_auto_apply.infrastructure.browser.hh_client import HHClient

logger.remove()
logger.add(sys.stderr, level="INFO")

def test_vacancy_with_saved_session():
    """Тестирует вакансию, используя сохранённую сессию браузера."""
    
    vacancy_url = "https://hh.ru/vacancy/132780378"
    
    print(f"\n{'='*70}")
    print(f"ТЕСТ ВАКАНСИИ 132780378 С СОХРАНЁННОЙ СЕССИЕЙ")
    print(f"{'='*70}\n")
    
    config = Config.from_env()
    client = HHClient(config)
    
    # Путь к сохранённой сессии
    session_path = Path(".hh_user")
    
    if not session_path.exists():
        print(f"[-] Папка с сессией не найдена: {session_path}")
        print(f"[!] Запустите сначала полный бот для сохранения сессии")
        return
    
    print(f"[✓] Используется сохранённая сессия: {session_path}\n")
    
    with sync_playwright() as p:
        # Используем сохранённый контекст браузера
        context = p.chromium.launch_persistent_context(
            str(session_path),
            headless=False,
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.set_default_timeout(30000)
        
        try:
            # Открываем вакансию
            print(f"[→] Переходу на вакансию...")
            page.goto(vacancy_url, wait_until="load", timeout=30000)
            page.wait_for_timeout(2000)
            print(f"[✓] Страница загружена\n")
            
            # Ищем кнопку откликнуться
            print(f"[→] Ищу кнопку 'Откликнуться'...")
            apply_btn = client.get_apply_button(page)
            
            if not apply_btn:
                print(f"[-] Кнопка не найдена\n")
                page.screenshot(path="test_no_button.png", full_page=True)
                return
            
            print(f"[✓] Кнопка найдена!\n")
            
            # Нажимаем
            print(f"[→] Нажимаю 'Откликнуться'...")
            apply_btn.click()
            page.wait_for_timeout(3000)
            print(f"[✓] Форма открыта\n")
            
            # Ищем вопросы
            print(f"[→] Ищу кастомные вопросы...")
            questions = client._detect_custom_questions(page)
            
            if not questions:
                print(f"[-] Вопросов не найдено\n")
                page.screenshot(path="test_no_questions.png", full_page=True)
            else:
                print(f"[✓] Найдено {len(questions)} вопросов:\n")
                
                for i, (field_name, question_text) in enumerate(questions.items(), 1):
                    print(f"  {i}. Поле: {field_name}")
                    print(f"     Вопрос: {question_text[:110]}...")
                    print()
                
                # Извлекаем резюме
                print(f"[→] Извлекаю контекст резюме...")
                resume = client._extract_resume_context(page)
                print(f"[✓] Должность: {resume.get('title')}")
                print(f"    Опыт: {resume.get('experience_years')} лет\n")
                
                # Генерируем ответы
                print(f"[→] Генерирую ответы через AI...")
                title = page.locator('h1[data-qa="vacancy-title"]').first.inner_text() or "Unknown"
                answers = client._generate_answers_for_custom_questions(questions, resume, title)
                
                if answers:
                    print(f"[✓] Получено {len(answers)} ответов:\n")
                    
                    for field_name, answer_text in answers.items():
                        print(f"  [{field_name}]")
                        print(f"  → {answer_text[:130]}...\n")
                    
                    # Заполняем
                    print(f"[→] Заполняю поля...")
                    success = client._fill_custom_questions(page, answers)
                    
                    if success:
                        print(f"[✓] Поля заполнены успешно!\n")
                        page.screenshot(path="test_success.png", full_page=True)
                        print(f"[✓] Скриншот сохранён: test_success.png\n")
                    else:
                        print(f"[-] Ошибка при заполнении\n")
                        page.screenshot(path="test_error.png", full_page=True)
                else:
                    print(f"[-] Не удалось сгенерировать ответы\n")
            
            print(f"[*] Окно остаётся открытым для проверки...")
            page.wait_for_timeout(30000)
            
        except Exception as e:
            print(f"[✗] ОШИБКА: {e}\n")
            logger.exception(e)
            page.screenshot(path="test_exception.png", full_page=True)
        
        finally:
            context.close()
    
    print(f"\n{'='*70}")
    print(f"[+] Тест завершён")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    test_vacancy_with_saved_session()
