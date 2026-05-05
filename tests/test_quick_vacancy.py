#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Быстрый тест: открыть вакансию и протестировать обнаружение вопросов.
"""
import sys
import os

if sys.platform == "win32":
    os.system("chcp 65001 > nul")

from playwright.sync_api import sync_playwright
from loguru import logger
from hh_auto_apply.core.config import Config
from hh_auto_apply.infrastructure.browser.hh_client import HHClient

logger.remove()
logger.add(sys.stderr, level="INFO")

def test_vacancy(vacancy_url: str):
    """Быстро тестирует вакансию."""
    
    print(f"\n{'='*70}")
    print(f"БЫСТРЫЙ ТЕСТ ВАКАНСИИ")
    print(f"{'='*70}")
    print(f"URL: {vacancy_url}\n")
    
    config = Config.from_env()
    client = HHClient(config)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        page.set_default_timeout(30000)
        
        try:
            # Открываем вакансию
            print("[→] Переходу на вакансию...")
            page.goto(vacancy_url, wait_until="load", timeout=30000)
            page.wait_for_timeout(2000)
            print("[✓] Страница загружена\n")
            
            # Ищем кнопку откликнуться
            print("[→] Ищу кнопку 'Откликнуться'...")
            apply_btn = client.get_apply_button(page)
            
            if not apply_btn:
                print("[-] Кнопка не найдена (может быть залогинены?)\n")
                page.screenshot(path="fail_no_button.png", full_page=True)
                return
            
            print("[✓] Кнопка найдена!\n")
            
            # Нажимаем
            print("[→] Нажимаю 'Откликнуться'...")
            apply_btn.click()
            page.wait_for_timeout(3000)
            print("[✓] Форма открыта\n")
            
            # Ищем вопросы
            print("[→] Ищу кастомные вопросы...")
            questions = client._detect_custom_questions(page)
            
            if not questions:
                print("[-] Вопросов не найдено\n")
                page.screenshot(path="fail_no_questions.png", full_page=True)
            else:
                print(f"[✓] Найдено {len(questions)} вопросов:\n")
                
                for i, (field_name, question_text) in enumerate(questions.items(), 1):
                    print(f"  {i}. Поле: {field_name}")
                    print(f"     Вопрос: {question_text[:120]}...")
                    print()
                
                # Извлекаем резюме
                print("[→] Извлекаю контекст резюме...")
                resume = client._extract_resume_context(page)
                print(f"[✓] Должность: {resume.get('title')}")
                print(f"    Опыт: {resume.get('experience_years')} лет\n")
                
                # Генерируем ответы
                print("[→] Генерирую ответы через AI...")
                title = page.locator('h1[data-qa="vacancy-title"]').first.inner_text() or "Unknown"
                answers = client._generate_answers_for_custom_questions(questions, resume, title)
                
                if answers:
                    print(f"[✓] Получено {len(answers)} ответов:\n")
                    
                    for field_name, answer_text in answers.items():
                        print(f"  Поле: {field_name}")
                        print(f"  Ответ: {answer_text[:150]}...")
                        print()
                    
                    # Заполняем
                    print("[→] Заполняю поля...")
                    success = client._fill_custom_questions(page, answers)
                    
                    if success:
                        print("[✓] Поля заполнены успешно!\n")
                        page.screenshot(path="success_filled.png", full_page=True)
                        print("[✓] Скриншот сохранён: success_filled.png\n")
                    else:
                        print("[-] Ошибка при заполнении\n")
                        page.screenshot(path="fail_fill.png", full_page=True)
                else:
                    print("[-] Не удалось сгенерировать ответы\n")
            
            print("[*] Окно остаётся открытым для просмотра...")
            page.wait_for_timeout(15000)
            
        except Exception as e:
            print(f"[✗] ОШИБКА: {e}\n")
            logger.exception(e)
            page.screenshot(path="fail_error.png", full_page=True)
        
        finally:
            context.close()
            browser.close()
    
    print(f"\n{'='*70}")
    print("[+] Тест завершён")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    test_vacancy("https://hh.ru/vacancy/132780378")
