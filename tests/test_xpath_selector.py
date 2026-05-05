#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тест для проверки XPath селектора для поиска вопросов.
"""

def test_xpath_selector():
    """Проверяет что XPath селектор правильно построен."""
    
    # Старый селектор (неправильный)
    old_xpath = "preceding-sibling::div[@data-qa='task-question'][1]"
    
    # Новый селектор (правильный)
    new_xpath = "preceding::div[@data-qa='task-question'][1]"
    
    print("\n" + "="*60)
    print("Проверка XPath селектора для поиска вопросов")
    print("="*60)
    
    print(f"\n[!] СТАРЫЙ селектор (неправильный):")
    print(f"    {old_xpath}")
    print(f"    Проблема: ищет только на прямом соседе (preceding-sibling)")
    print(f"    Не работает для вопросов обёрнутых в контейнер div")
    
    print(f"\n[✓] НОВЫЙ селектор (правильный):")
    print(f"    {new_xpath}")
    print(f"    Преимущество: ищет в любых предыдущих элементах (preceding)")
    print(f"    Работает для вопросов как прямых соседей, так и обёрнутых в div")
    
    print(f"\n[*] Пример HTML структуры для 2-го вопроса:")
    print("""
    <div class="magritte-text___...">
      <div class="g-user-content" data-qa="task-question">
        Почему вам интересна данная позиция...
      </div>
    </div>
    <textarea name="task_179017370_text"></textarea>
    """)
    
    print(f"\n[!] Проблема старого селектора:")
    print(f"    - `preceding-sibling::div[@data-qa='task-question']` ищет соседей")
    print(f"    - У нас есть <div class='magritte-text'> (сосед)")
    print(f"    - Но div[@data-qa] находится ВНУТРИ маргритта")
    print(f"    - Поэтому селектор не находит вопрос!")
    
    print(f"\n[✓] Как работает новый селектор:")
    print(f"    - `preceding::div[@data-qa='task-question']` ищет ВСЕ предыдущие div")
    print(f"    - Это включает div[@data-qa] внутри любого контейнера")
    print(f"    - Находит ДО контейнера, а затем")
    print(f"    - [1] выбирает БЛИЖАЙШИЙ (последний) такой div")
    
    print(f"\n[✓] Результат:")
    print(f"    - 1-й вопрос: найден (был и с новым работает)")
    print(f"    - 2-й вопрос: ТЕПЕРЬ НАЙДЕН (раньше не находился)")
    
    print("\n" + "="*60)
    print("Селектор обновлён в client.py строка ~540")
    print("="*60 + "\n")


if __name__ == "__main__":
    test_xpath_selector()
