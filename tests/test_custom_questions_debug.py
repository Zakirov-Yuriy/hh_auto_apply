#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Отладочный скрипт для тестирования обнаружения и заполнения кастомных вопросов.
Используется для проверки конкретной вакансии.
"""
import sys
import os

# Установка UTF-8 кодировки для Windows консоли
if sys.platform == "win32":
    os.system("chcp 65001 > nul")

from pathlib import Path
from playwright.sync_api import sync_playwright
from loguru import logger
from hh_auto_apply.core.config import Config
from hh_auto_apply.infrastructure.browser.hh_client import HHClient

# Настройка логирования
logger.remove()
logger.add(sys.stderr, level="DEBUG")

def test_custom_questions(vacancy_url: str):
    """Тестирует обнаружение и генерацию ответов на кастомные вопросы."""
    
    print(f"\n{'='*60}")
    print(f"Тестирование: {vacancy_url}")
    print(f"{'='*60}\n")
    
    # Загружаем конфигурацию
    config = Config.from_env()
    
    # Создаём HHClient
    client = HHClient(config)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.set_default_timeout(30000)
        
        try:
            # Переходим на страницу вакансии
            print(f"[*] Открываю вакансию: {vacancy_url}\n")
            try:
                page.goto(vacancy_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"[!] Ошибка при загрузке (timeout?): {e}")
                print(f"[*] Пытаюсь загрузить без ожидания контента...\n")
                page.goto(vacancy_url, wait_until="load", timeout=15000)
            
            page.wait_for_timeout(1000)
            
            # Получаем название вакансии
            title_selectors = [
                'h1[data-qa="vacancy-title"]',
                'h1[class*="title"]',
                'span[data-qa*="title"]',
            ]
            title = "Unknown"
            for sel in title_selectors:
                try:
                    elem = page.locator(sel).first
                    if elem:
                        text = elem.inner_text()
                        if text:
                            title = text.strip()
                            break
                except Exception:
                    continue
            
            print(f"[+] Название вакансии: {title}\n")
            
            # Ищем и нажимаем кнопку "Откликнуться"
            print("[*] Ищу кнопку 'Откликнуться'...\n")
            try:
                apply_btn = client.get_apply_button(page)
                if not apply_btn:
                    print("[-] Кнопка 'Откликнуться' не найдена!")
                    print("[i] Вероятно, требуется авторизация.\n")
                    page.screenshot(path="debug_no_apply_btn.png", full_page=True)
                    return
            except Exception as e:
                print(f"[-] Ошибка при поиске кнопки: {e}\n")
                page.screenshot(path="debug_search_error.png", full_page=True)
                return
            
            apply_btn = client.get_apply_button(page)
            
            if apply_btn:
                print("[+] Кнопка найдена! Нажимаю...\n")
                try:
                    apply_btn.click()
                    page.wait_for_timeout(3000)
                    print("[+] Форма открыта!\n")
                except Exception as e:
                    print(f"[-] Ошибка при нажатии кнопки: {e}\n")
                    page.screenshot(path="debug_click_error.png", full_page=True)
                    return
            else:
                print("[-] Кнопка не найдена.\n")
                page.screenshot(path="debug_no_button.png", full_page=True)
                return
            
            # Ищем кастомные вопросы
            print("[*] Ищу кастомные вопросы на форме...\n")
            custom_questions = client._detect_custom_questions(page)
            
            if custom_questions:
                print(f"[+] Найдено {len(custom_questions)} кастомных вопросов:\n")
                for field_name, question_text in custom_questions.items():
                    print(f"  [?] {field_name}:")
                    print(f"      {question_text[:150]}...")
                    print()
                
                # Извлекаем контекст резюме
                print("[*] Извлекаю контекст резюме...\n")
                resume_context = client._extract_resume_context(page)
                print(f"  Должность: {resume_context.get('title')}")
                print(f"  Зарплата: {resume_context.get('salary')} {resume_context.get('currency')}")
                print(f"  Опыт: {resume_context.get('experience_years')} лет")
                print(f"  Навыки: {resume_context.get('skills')}")
                print()
                
                # Генерируем ответы
                print("[*] Генерирую ответы с помощью AI...\n")
                answers = client._generate_answers_for_custom_questions(
                    custom_questions,
                    resume_context,
                    title
                )
                
                if answers:
                    print(f"[+] Получено {len(answers)} ответов:\n")
                    for field_name, answer_text in answers.items():
                        print(f"  [A] {field_name}:")
                        print(f"      {answer_text[:200]}")
                        print()
                    
                    # Заполняем поля
                    print("[*] Заполняю кастомные поля...\n")
                    success = client._fill_custom_questions(page, answers)
                    
                    if success:
                        print("[+] Поля успешно заполнены!\n")
                        print("[*] Скриншот формы (сохранён для проверки):\n")
                        page.screenshot(path="debug_custom_form.png", full_page=True)
                        print("    Файл: debug_custom_form.png\n")
                    else:
                        print("[-] Не удалось заполнить все поля.\n")
                else:
                    print("[-] Не удалось сгенерировать ответы.\n")
            else:
                print("[i] На этой форме нет кастомных вопросов.\n")
            
            # Ждём перед закрытием для просмотра результата
            print("\n[*] Оставляю окно открытым на 10 секунд для проверки...\n")
            page.wait_for_timeout(10000)
            
        except Exception as e:
            logger.exception(f"Ошибка при тестировании: {e}")
        
        finally:
            context.close()
            browser.close()
    
    print(f"\n{'='*60}")
    print("[+] Тест завершён")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # Тестируем конкретную вакансию
    vacancy_url = "https://hh.ru/vacancy/132780378"
    test_custom_questions(vacancy_url)
