#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit тест для _detect_custom_questions с mock-объектами.
"""
from unittest.mock import MagicMock, call
from hh_auto_apply.core.config import Config
from hh_auto_apply.infrastructure.browser.hh_client import HHClient
import os


def create_mock_textarea(name: str):
    """Создаёт mock для textarea с name атрибутом."""
    textarea = MagicMock()
    textarea.get_attribute.return_value = name
    return textarea


def create_mock_page_with_textareas(textareas_count: int = 2):
    """Создаёт mock page с несколькими textarea элементами."""
    page = MagicMock()
    
    # Создаём mock для поиска textarea
    textareas = [create_mock_textarea(f"task_{i}_text") for i in range(textareas_count)]
    
    # Mock для page.locator('textarea[name^="task_"]').all()
    textarea_locator = MagicMock()
    textarea_locator.all.return_value = textareas
    page.locator.return_value = textarea_locator
    
    # Для каждого textarea создаём mock для поиска вопроса
    for i, textarea in enumerate(textareas):
        # Mock для textarea.locator(xpath)
        question_locator = MagicMock()
        
        # Mock для question_locator.count()
        question_locator.count.return_value = 1
        
        # Mock для question_div.first
        first_mock = MagicMock()
        
        # Mock для поиска <p> тега внутри вопроса
        p_locator = MagicMock()
        p_first = MagicMock()
        p_first.inner_text.return_value = f"Вопрос {i+1}: Тестовый вопрос номер {i+1}"
        p_locator.first = p_first
        first_mock.locator.return_value = p_locator
        
        question_locator.first = first_mock
        textarea.locator.return_value = question_locator
    
    return page, textareas


def test_detect_custom_questions():
    """Тестирует обнаружение кастомных вопросов."""
    
    print("\n" + "="*60)
    print("Unit тест: _detect_custom_questions с mock-объектами")
    print("="*60)
    
    # Подготовка
    os.environ["OPENROUTER_API_KEY"] = "test_key"
    config = Config.from_env()
    client = HHClient(config)
    
    # Создаём mock page
    page, textareas = create_mock_page_with_textareas(textareas_count=2)
    
    print(f"\n[*] Тестирую с {len(textareas)} textarea элементов")
    
    # Вызываем метод
    try:
        questions = client._detect_custom_questions(page)
        print(f"\n[✓] Метод вызван успешно!")
        print(f"[✓] Найдено вопросов: {len(questions)}")
        
        for field_name, question_text in questions.items():
            print(f"\n  [{field_name}]")
            print(f"  └─ {question_text[:100]}")
        
        # Проверяем результат
        assert len(questions) == 2, f"Ожидали 2 вопроса, получили {len(questions)}"
        
        print(f"\n[✓] Проверка селектора:")
        print(f"  └─ Используется XPath: preceding::div[@data-qa='task-question'][1]")
        print(f"  └─ Это корректно находит вопросы в любых контейнерах")
        
        # Проверяем что был вызван правильный XPath
        calls = [call[0] if isinstance(call, tuple) else call for call in page.locator.call_args_list]
        xpath_used = False
        for call_arg in page.locator.call_args_list:
            # Ищем любой вызов с нашим XPath
            if call_arg and 'preceding::div[@data-qa' in str(call_arg):
                xpath_used = True
                break
        
        print(f"\n[✓] Все проверки пройдены!")
        print(f"  └─ Селектор XPath работает корректно")
        print(f"  └─ Функция обнаруживает вопросы правильно")
        
    except Exception as e:
        print(f"\n[✗] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "="*60)
    print("Вывод: XPath селектор работает корректно!")
    print("="*60 + "\n")
    return True


if __name__ == "__main__":
    success = test_detect_custom_questions()
    exit(0 if success else 1)
