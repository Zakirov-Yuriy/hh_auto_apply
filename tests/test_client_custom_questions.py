"""
Тесты для методов обработки кастомных вопросов в HHClient.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch

from hh_auto_apply.core.config import Config
from hh_auto_apply.infrastructure.browser.hh_client import HHClient


@pytest.fixture
def mock_config():
    """Создаёт mock Config для тестов."""
    config = Mock(spec=Config)
    config.screenshots_dir = "screenshots"
    config.search_query = "python"
    config.use_ai_cover_letter = True
    config.ai_model = "openai/gpt-oss-120b:free"
    config.base_url = "https://hh.ru"
    config.min_sleep = 1.0
    config.max_sleep = 2.0
    config.require_cover_letter = False
    config.fail_if_resume_not_found = False
    return config


@pytest.fixture
def mock_page():
    """Создаёт mock Page для тестов."""
    page = Mock()
    return page


@pytest.fixture
def client(mock_config):
    """Создаёт HHClient с mock конфигом."""
    with patch('hh_auto_apply.client.APIKeyRotator'):
        client = HHClient(mock_config)
        # Создаём mock ротатор
        client.key_rotator = Mock()
        client.key_rotator.get_current_key.return_value = "test_key_123"
        client.key_rotator.has_multiple_keys.return_value = False
    return client


class TestDetectCustomQuestions:
    """Тесты для метода _detect_custom_questions."""
    
    def test_detect_custom_questions_finds_textareas(self, client, mock_page):
        """Проверяет что метод находит textarea с кастомными вопросами."""
        # Настраиваем mock textarea
        mock_textarea1 = Mock()
        mock_textarea1.get_attribute.side_effect = lambda attr: "task_179017369_text" if attr == "name" else None
        
        # Настраиваем label locator для поиска вопроса
        mock_label = Mock()
        mock_label.count.return_value = 1
        mock_label.first.inner_text.return_value = "What is your salary expectation?"
        
        mock_textarea1.locator.return_value = Mock()
        
        # Настраиваем locator для поиска textareas
        mock_locator = Mock()
        mock_locator.all.return_value = [mock_textarea1]
        
        # Настраиваем mock Page locator
        def locator_side_effect(selector):
            if "textarea[name^=" in selector:
                return mock_locator
            elif "label[for=" in selector:
                return mock_label
            return Mock(count=lambda: 0)
        
        mock_page.locator.side_effect = locator_side_effect
        
        # Вызываем метод
        questions = client._detect_custom_questions(mock_page)
        
        # Проверяем результат
        assert len(questions) > 0
        assert "task_179017369_text" in questions
    
    def test_detect_custom_questions_empty_form(self, client, mock_page):
        """Проверяет обработку формы без кастомных вопросов."""
        # Настраиваем mock Page - нет textareas
        mock_locator = Mock()
        mock_locator.all.return_value = []
        mock_page.locator.return_value = mock_locator
        
        # Вызываем метод
        questions = client._detect_custom_questions(mock_page)
        
        # Проверяем результат
        assert questions == {}
    
    def test_detect_custom_questions_handles_exception(self, client, mock_page):
        """Проверяет обработку исключений при обнаружении вопросов."""
        # Настраиваем mock Page для выброса исключения
        mock_page.locator.side_effect = Exception("Page error")
        
        # Вызываем метод - должен вернуть пустой словарь без выброса исключения
        questions = client._detect_custom_questions(mock_page)
        
        # Проверяем результат
        assert questions == {}


class TestExtractResumeContext:
    """Тесты для метода _extract_resume_context."""
    
    def test_extract_resume_context_returns_dict(self, client, mock_page):
        """Проверяет что метод возвращает словарь с контекстом."""
        # Не настраиваем специфические мокираны - используем дефолтные значения
        mock_page.inner_text.return_value = "Some resume with 130 ₽"
        
        # Вызываем метод
        context = client._extract_resume_context(mock_page)
        
        # Проверяем результат
        assert isinstance(context, dict)
        assert "title" in context
        assert "salary" in context
        assert "currency" in context
    
    def test_extract_resume_context_default_values(self, client, mock_page):
        """Проверяет что метод возвращает дефолтные значения."""
        mock_page.locator.side_effect = Exception("Mock error")
        mock_page.inner_text.return_value = ""
        
        # Вызываем метод
        context = client._extract_resume_context(mock_page)
        
        # Проверяем результат с дефолтными значениями
        assert context["title"] == "Python Backend Developer"
        assert context["salary"] == "130000"
        assert context["currency"] == "RUR"


class TestGenerateAnswersForCustomQuestions:
    """Тесты для метода _generate_answers_for_custom_questions."""
    
    @patch('hh_auto_apply.client.requests.post')
    def test_generate_answers_makes_api_call(self, mock_post, client):
        """Проверяет что метод делает API запрос к OpenRouter."""
        # Настраиваем mock ответ API
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Generated answer text"
                }
            }]
        }
        mock_post.return_value = mock_response
        
        # Подготавливаем входные данные
        questions = {
            "task_179017369_text": "What is your salary expectation?"
        }
        resume_context = {
            "title": "Python Developer",
            "salary": "130000",
            "currency": "RUR"
        }
        
        # Вызываем метод
        answers = client._generate_answers_for_custom_questions(
            questions, 
            resume_context, 
            "Engineer"
        )
        
        # Проверяем что был сделан запрос
        assert mock_post.called
        assert len(answers) > 0
    
    @patch('hh_auto_apply.client.requests.post')
    def test_generate_answers_handles_api_error(self, mock_post, client):
        """Проверяет обработку ошибок API."""
        # Настраиваем mock ответ с ошибкой
        mock_post.side_effect = Exception("API Error")
        
        # Подготавливаем входные данные
        questions = {
            "task_179017369_text": "What is your salary expectation?"
        }
        resume_context = {
            "title": "Python Developer",
            "salary": "130000"
        }
        
        # Вызываем метод - должен вернуть пустой словарь без выброса исключения
        answers = client._generate_answers_for_custom_questions(
            questions, 
            resume_context, 
            "Engineer"
        )
        
        # Проверяем результат
        assert isinstance(answers, dict)


class TestFillCustomQuestions:
    """Тесты для метода _fill_custom_questions."""
    
    def test_fill_custom_questions_empty_answers(self, client, mock_page):
        """Проверяет обработку пустого словаря ответов."""
        # Вызываем метод с пустыми ответами
        result = client._fill_custom_questions(mock_page, {})
        
        # Проверяем результат
        assert result is True  # Успех для пустого набора
    
    def test_fill_custom_questions_fills_textareas(self, client, mock_page):
        """Проверяет заполнение textarea полей."""
        # Настраиваем mock textarea
        mock_textarea = Mock()
        mock_textarea.is_visible.return_value = True
        mock_textarea.input_value.return_value = "Generated answer"
        
        # Настраиваем mock Page
        mock_locator = Mock()
        mock_locator.first = mock_textarea
        mock_page.locator.return_value = mock_locator
        mock_page.keyboard = Mock()
        
        # Подготавливаем ответы для заполнения
        answers = {
            "task_179017369_text": "Generated answer text"
        }
        
        # Мокируем is_visible
        with patch.object(client, 'is_visible', return_value=True):
            # Вызываем метод
            result = client._fill_custom_questions(mock_page, answers)
        
        # Проверяем результат
        assert result is True
        assert mock_textarea.click.called
        assert mock_page.keyboard.press.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
