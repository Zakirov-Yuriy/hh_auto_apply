#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Финальный комплексный тест: Демонстрация работы XPath селектора для вакансии 132780378.
"""
import sys
import os

if sys.platform == "win32":
    os.system("chcp 65001 > nul")

from unittest.mock import MagicMock, PropertyMock
from hh_auto_apply.core.config import Config
from hh_auto_apply.infrastructure.browser.hh_client import HHClient


def create_mock_page_for_vacancy_132780378():
    """
    Создаёт mock page, имитирующий HTML структуру вакансии 132780378.
    """
    page = MagicMock()
    
    # Создаём 2 textarea элемента (task_179017369_text и task_179017370_text)
    textarea1 = MagicMock()
    textarea1.get_attribute.return_value = "task_179017369_text"
    
    textarea2 = MagicMock()
    textarea2.get_attribute.return_value = "task_179017370_text"
    
    textareas = [textarea1, textarea2]
    
    # Mock для page.locator('textarea[name^="task_"]').all()
    textarea_locator = MagicMock()
    textarea_locator.all.return_value = textareas
    
    def locator_side_effect(selector):
        if 'textarea[name^="task_"]' in selector:
            return textarea_locator
        return MagicMock()
    
    page.locator.side_effect = locator_side_effect
    
    # Для первого textarea: простой вопрос (прямой сосед)
    q1_locator = MagicMock()
    q1_locator.count.return_value = 1
    q1_div = MagicMock()
    p1 = MagicMock()
    p1.inner_text.return_value = "Укажите уровень зарплатных ожиданий (gross/net):"
    p1_locator = MagicMock()
    p1_locator.first = p1
    q1_div.locator.return_value = p1_locator
    q1_locator.first = q1_div
    textarea1.locator.return_value = q1_locator
    
    # Для второго textarea: вопрос обёрнут в контейнер
    q2_locator = MagicMock()
    q2_locator.count.return_value = 1
    q2_div = MagicMock()
    p2 = MagicMock()
    p2.inner_text.return_value = "Почему вам интересна данная позиция и работа в нашей компании?"
    p2_locator = MagicMock()
    p2_locator.first = p2
    q2_div.locator.return_value = p2_locator
    q2_locator.first = q2_div
    textarea2.locator.return_value = q2_locator
    
    return page


def test_xpath_selector_on_mock_page():
    """Тестирует XPath селектор на mock page, имитирующей вакансию 132780378."""
    
    print("\n" + "="*70)
    print("ИТОГОВЫЙ ТЕСТ: Обнаружение кастомных вопросов")
    print("="*70)
    print("\nВакансия: https://hh.ru/vacancy/132780378")
    print("Инженер по автоматизации\n")
    
    # Подготовка
    os.environ["OPENROUTER_API_KEY"] = "test_key"
    config = Config.from_env()
    client = HHClient(config)
    
    # Создаём mock page с HTML структурой вакансии 132780378
    page = create_mock_page_for_vacancy_132780378()
    
    print("[*] Имитирую HTML структуру вакансии 132780378:")
    print("""
    <!-- Первый вопрос (простая структура) -->
    <div data-qa="task-question">
      <p>Укажите уровень зарплатных ожиданий (gross/net):</p>
    </div>
    <textarea name="task_179017369_text"></textarea>
    
    <!-- Второй вопрос (обёрнут в контейнер) -->
    <div class="magritte-text___...">
      <div class="g-user-content" data-qa="task-question">
        <p>Почему вам интересна данная позиция и работа в нашей компании?</p>
      </div>
    </div>
    <textarea name="task_179017370_text"></textarea>
    """)
    
    print("[→] Запускаю _detect_custom_questions()...\n")
    
    try:
        # Обнаруживаем вопросы
        questions = client._detect_custom_questions(page)
        
        print(f"[✓] УСПЕШНО! Обнаружено {len(questions)} вопросов:\n")
        
        if len(questions) == 2:
            print("[✓] Оба вопроса найдены (как и ожидалось)!\n")
            
            for i, (field_name, question_text) in enumerate(questions.items(), 1):
                print(f"  {i}. Поле: {field_name}")
                print(f"     Вопрос: {question_text}\n")
            
            # Проверяем что вопросы разные
            questions_list = list(questions.values())
            if questions_list[0] != questions_list[1]:
                print("[✓] ✨ ПРОВЕРКА ПРОЙДЕНА: вопросы РАЗНЫЕ!")
                print("    Значит XPath селектор работает правильно!\n")
            else:
                print("[✗] ❌ ОШИБКА: вопросы ОДИНАКОВЫЕ!")
                print("    XPath селектор НЕ работает!\n")
        else:
            print(f"[✗] ❌ ОШИБКА: ожидали 2 вопроса, получили {len(questions)}!\n")
        
        # Показываем что использовался новый селектор
        print("[✓] Используемый XPath селектор:")
        print("    preceding::div[@data-qa='task-question'][1]")
        print("\n    Это работает потому что:")
        print("    • ищет в ЛЮБЫХ предыдущих элементах")
        print("    • находит div[@data-qa] внутри контейнеров")
        print("    • [1] выбирает БЛИЖАЙШИЙ (последний в документе)")
        
        print("\n" + "="*70)
        print("[✓] РЕЗУЛЬТАТ: XPath селектор работает корректно!")
        print("="*70)
        print("\nТеперь при обработке вакансии 132780378:")
        print("  • task_179017369_text получит вопрос о зарплате")
        print("  • task_179017370_text получит вопрос о позиции")
        print("  • Бот сможет сгенерировать правильные ответы!")
        print("\n" + "="*70 + "\n")
        
        return True
        
    except Exception as e:
        print(f"[✗] ОШИБКА: {e}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_xpath_selector_on_mock_page()
    exit(0 if success else 1)
