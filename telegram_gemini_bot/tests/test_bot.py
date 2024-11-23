import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone
import json
import os
from .helpers import AsyncTestHelper
import asyncio
from datetime import datetime, timezone
import json
import os
from unittest.mock import Mock, AsyncMock, patch
from telegram_gemini_bot.core.gemini_client import GeminiClient, GeminiResponse
from telegram_gemini_bot.core.message_router import MessageRouter, MessageContext
from telegram_gemini_bot.features.history.manager import HistoryManager
from telegram_gemini_bot.features.summary.analyzer import ChatAnalyzer
from telegram_gemini_bot.features.summary.generator import SummaryGenerator
from telegram_gemini_bot.handlers.message_handlers import MessageHandlers
from telegram_gemini_bot.handlers.command_handlers import CommandHandlers
import warnings

# Игнорируем предупреждения о незавершенных корутинах в тестах
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Фикстуры для тестирования
@pytest.fixture
def mock_gemini():
    """Мок для Gemini API"""
    with patch("google.generativeai.GenerativeModel") as mock_model, \
            patch("google.generativeai.configure"):
        client = GeminiClient(api_key="test_key")

        # Создаем моки для основных методов
        client.generate_text = AsyncMock(return_value=GeminiResponse(
            success=True,
            text="Test response"
        ))
        client.generate_with_image = AsyncMock(return_value=GeminiResponse(
            success=True,
            text="Image description"
        ))

        # Настраиваем моки для внутренних методов
        client._initialize_model = Mock(return_value=mock_model.return_value)
        client._get_safety_settings = Mock(return_value={})

        yield client

@pytest.fixture
def history_manager(tmp_path):
    """Менеджер истории с временной директорией"""
    return HistoryManager(storage_dir=str(tmp_path))


@pytest.fixture
def message_router():
    """Роутер сообщений с тестовыми триггерами"""
    return MessageRouter(default_triggers={'test', 'bot'})


@pytest.fixture
def chat_analyzer():
    """Анализатор чата"""
    return ChatAnalyzer()


# Тесты для GeminiClient
@pytest.mark.asyncio
async def test_gemini_text_generation(mock_gemini):
    """Тест генерации текста"""
    # Мокаем метод generate_text напрямую
    mock_gemini.generate_text = AsyncMock(return_value=GeminiResponse(
        success=True,
        text="Test response"
    ))

    response = await mock_gemini.generate_text("Test prompt")

    assert response.success
    assert response.text == "Test response"
    assert mock_gemini.generate_text.called
    assert mock_gemini.generate_text.call_args[0][0] == "Test prompt"


@pytest.mark.asyncio
async def test_gemini_image_generation(mock_gemini, tmp_path):
    """Тест генерации ответа на изображение"""
    # Создаём тестовое изображение
    test_image = tmp_path / "test.jpg"
    test_image.write_bytes(b"fake image data")

    # Мокаем метод generate_with_image напрямую
    mock_gemini.generate_with_image = AsyncMock(return_value=GeminiResponse(
        success=True,
        text="Image description"
    ))

    response = await mock_gemini.generate_with_image(
        prompt="Describe image",
        image_path=str(test_image)
    )

    assert response.success
    assert response.text == "Image description"


# Тесты для HistoryManager
def test_history_manager_add_message(history_manager):
    """Тест добавления сообщения в историю"""
    chat_id = "test_chat"
    message = {
        'message_id': 1,
        'from_user': {'id': 123, 'username': 'test_user'},
        'text': 'Test message'
    }

    history_manager.add_message(chat_id, message)
    messages = history_manager.get_messages(chat_id)

    assert len(messages) == 1
    assert messages[0]['text'] == 'Test message'


def test_history_manager_clear_history(history_manager):
    """Тест очистки истории"""
    chat_id = "test_chat"
    message = {
        'message_id': 1,
        'from_user': {'id': 123, 'username': 'test_user'},
        'text': 'Test message'
    }

    history_manager.add_message(chat_id, message)
    history_manager.clear_chat_history(chat_id)
    messages = history_manager.get_messages(chat_id)

    assert len(messages) == 0


# Тесты для ChatAnalyzer
def test_chat_analyzer_basic_stats(chat_analyzer):
    """Тест базовой статистики чата"""
    messages = [
        {
            'from_user': 'user1',
            'text': 'Hello',
            'date_unixtime': str(int(datetime.now(timezone.utc).timestamp()))
        },
        {
            'from_user': 'user2',
            'text': 'Hi there',
            'date_unixtime': str(int(datetime.now(timezone.utc).timestamp()))
        }
    ]

    analysis = chat_analyzer.analyze_messages(messages)

    assert analysis.total_messages == 2
    assert len(analysis.active_users) == 2
    assert 'user1' in analysis.active_users
    assert 'user2' in analysis.active_users


# Тесты для MessageRouter
def test_message_router_triggers():
    """Тест обработки триггеров"""
    router = MessageRouter(default_triggers={'test'})

    # Добавляем триггер
    router.add_chat_trigger('chat1', 'new_trigger')
    triggers = router.get_chat_triggers('chat1')

    assert 'new_trigger' in triggers
    assert 'test' in triggers

    # Удаляем триггер
    router.remove_chat_trigger('chat1', 'new_trigger')
    triggers = router.get_chat_triggers('chat1')

    assert 'new_trigger' not in triggers
    assert 'test' in triggers


# Тесты для обработчиков
@pytest.mark.asyncio
async def test_message_handler_text(mock_gemini):
    """Тест обработки текстового сообщения"""
    handlers = MessageHandlers(
        history_manager=Mock(),
        gemini_client=mock_gemini
    )

    update = AsyncMock()  # Используем AsyncMock вместо Mock
    update.effective_message.text = "Test message"
    update.effective_message.from_user.username = "test_user"
    update.effective_chat.type = "private"
    update.effective_chat.id = "test_chat"

    context = Mock()
    context.chat_data = {}

    # Мокаем метод generate_text
    mock_gemini.generate_text = AsyncMock(return_value=GeminiResponse(
        success=True,
        text="Test response"
    ))

    await handlers.handle_text_message(update, context)

    # Проверяем, что метод был вызван
    mock_gemini.generate_text.assert_called_once()
    update.effective_message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_command_handler_help():
    """Тест команды /help"""
    handlers = CommandHandlers(
        history_manager=Mock(),
        gemini_client=Mock()
    )

    update = AsyncMock()
    update.message = AsyncMock()
    context = Mock()

    await handlers.handle_help(update, context)

    update.message.reply_text.assert_called_once()


# Интеграционные тесты
@pytest.fixture
async def async_mock_helper():
    """Фикстура для работы с асинхронными моками"""
    return AsyncTestHelper()


@pytest.mark.asyncio
async def test_full_message_flow(
    mock_gemini: GeminiClient,
    history_manager: HistoryManager,
    async_mock_helper: AsyncTestHelper
) -> None:
    """Тест полного цикла обработки сообщения"""
    # Настраиваем моки с возвращаемыми значениями
    mock_gemini.generate_text = await async_mock_helper.awaited_mock(
        return_value=GeminiResponse(success=True, text="Test response")
    )

    # Мокаем методы history_manager
    history_manager.add_message = Mock()
    history_manager.get_messages = Mock(return_value=[
        {
            'text': 'Test message',
            'from_user': 'test_user'
        },
        {
            'text': 'Test response',
            'from_user': 'bot'
        }
    ])

    message_handlers = MessageHandlers(
        history_manager=history_manager,
        gemini_client=mock_gemini
    )

    # Создаём базовые моки
    message_mock = await async_mock_helper.awaited_mock()
    user_mock = await async_mock_helper.awaited_mock()
    chat_mock = await async_mock_helper.awaited_mock()
    reply_mock = await async_mock_helper.awaited_mock()
    bot_mock = await async_mock_helper.awaited_mock()

    # Настраиваем структуру моков
    update = AsyncMock()
    update.effective_message = message_mock
    update.effective_message.from_user = user_mock
    update.effective_chat = chat_mock
    update.effective_message.reply_text = reply_mock

    # Настраиваем данные
    update.effective_message.text = "Test message"
    update.effective_message.from_user.username = "test_user"
    update.effective_message.from_user.id = 123
    update.effective_chat.id = "test_chat"
    update.effective_chat.type = "private"

    context = AsyncMock()
    context.chat_data = {}
    context.bot = bot_mock
    context.bot.id = 999
    context.bot.username = "test_bot"

    try:
        # Выполняем тест
        await async_mock_helper.run_with_timeout(
            message_handlers.handle_text_message(update, context)
        )

        # Проверяем результаты
        assert history_manager.add_message.call_count == 2
        assert mock_gemini.generate_text.called
        assert reply_mock.called

        messages = history_manager.get_messages("test_chat")
        assert len(messages) == 2
        assert messages[0]['text'] == "Test message"
        assert messages[1]['text'] == "Test response"

    finally:
        # Очищаем моки
        await async_mock_helper.cleanup_mocks(
            mock_gemini.generate_text,
            message_mock,
            user_mock,
            chat_mock,
            reply_mock,
            bot_mock
        )
        await async_mock_helper.cleanup_tasks()

if __name__ == '__main__':
    pytest.main([__file__])
