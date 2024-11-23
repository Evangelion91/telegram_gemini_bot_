import asyncio
import nest_asyncio
from telegram.ext import ApplicationBuilder, MessageHandler, filters

from config import BotConfig
from core.bot_manager import BotManager
from core.gemini_client import GeminiClient
from features.history.manager import HistoryManager
from features.summary.generator import SummaryGenerator
from handlers.command_handlers import CommandHandlers
from handlers.message_handlers import MessageHandlers
from utils.logger import setup_logging


async def main():
    """Инициализация и запуск бота"""
    # Загружаем конфигурацию
    config = BotConfig.from_env()
    config.validate()

    # Настраиваем логирование
    logger = setup_logging(
        log_level=config.LOG_LEVEL,
        log_dir=config.LOG_DIR
    )
    main_logger = logger.get_child("main")
    main_logger.info("Starting bot initialization...")

    try:
        # Инициализируем компоненты
        history_manager = HistoryManager(
            storage_dir=config.HISTORY_DIR,
            logger=logger.get_child("history")
        )

        gemini_client = GeminiClient(
            api_key=config.GEMINI_API_KEY,
            model_name=config.GEMINI_MODEL_NAME,
            logger=logger.get_child("gemini")
        )

        bot_manager = BotManager(
            telegram_token=config.TELEGRAM_TOKEN,
            gemini_api_key=config.GEMINI_API_KEY,
            default_triggers=config.DEFAULT_TRIGGERS,
            logger=logger.get_child("bot_manager")
        )

        # Инициализируем обработчики
        command_handlers = CommandHandlers(
            history_manager=history_manager,
            gemini_client=gemini_client,
            logger=logger.get_child("commands")
        )

        message_handlers = MessageHandlers(
            history_manager=history_manager,
            gemini_client=gemini_client,
            logger=logger.get_child("messages")
        )

        # Регистрируем обработчики команд
        for command, handler in command_handlers.commands.items():
            bot_manager.application.add_handler(
                CommandHandler(command, handler)
            )
            main_logger.info(f"Registered command handler: /{command}")

        # Регистрируем обработчики сообщений
        bot_manager.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                message_handlers.handle_text_message
            )
        )

        bot_manager.application.add_handler(
            MessageHandler(
                filters.PHOTO,
                message_handlers.handle_image_message
            )
        )

        bot_manager.application.add_handler(
            MessageHandler(
                filters.StatusUpdate.NEW_CHAT_MEMBERS,
                message_handlers.handle_new_chat_members
            )
        )

        # Проверяем доступность Telegram API
        main_logger.info("Checking Telegram API access...")
        bot_info = await bot_manager.application.bot.get_me()
        main_logger.info(f"Bot initialized: {bot_info.first_name} (@{bot_info.username})")

        # Отправляем сообщение админу о запуске
        if config.ADMIN_CHAT_ID:
            await bot_manager.application.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text="🚀 Бот успешно запущен и готов к работе."
            )

        # Запускаем бота
        main_logger.info("Starting bot polling...")
        await bot_manager.application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        main_logger.error(f"Critical error during bot initialization: {e}")
        raise

    if __name__ == "__main__":
        # Применяем nest_asyncio для работы в jupyter/ipython
        nest_asyncio.apply()

        # Запускаем бота
        asyncio.run(main())