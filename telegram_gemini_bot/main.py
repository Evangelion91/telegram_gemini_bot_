# telegram_gemini_bot/main.py
import asyncio
import nest_asyncio
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,  # Добавляем импорт
    MessageHandler,
    filters,
    CallbackContext
)
from telegram import Update
from telegram_gemini_bot.config import BotConfig
from telegram_gemini_bot.core.bot_manager import BotManager
from telegram_gemini_bot.core.gemini_client import GeminiClient
from telegram_gemini_bot.features.history.manager import HistoryManager
from telegram_gemini_bot.handlers.command_handlers import CommandHandlers
from telegram_gemini_bot.handlers.message_handlers import MessageHandlers
from telegram_gemini_bot.utils.logger import setup_logging

nest_asyncio.apply()


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
                (filters.TEXT & ~filters.COMMAND & (
                        filters.Regex(r'@ChoYaPropustil_bot') |  # Упоминание бота
                        filters.REPLY & filters.ChatType.GROUPS  # Ответ на сообщение бота в группах
                )) | filters.ChatType.PRIVATE,  # Или личные сообщения
                message_handlers.handle_text_message
            )
        )

        bot_manager.application.add_handler(
            MessageHandler(
                (filters.PHOTO & ~filters.COMMAND & (
                        filters.Regex(r'@ChoYaPropustil_bot') |  # Упоминание бота
                        filters.REPLY & filters.ChatType.GROUPS  # Ответ на сообщение бота в группах
                )) | filters.ChatType.PRIVATE,  # Или личные сообщения
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
            try:
                await bot_manager.application.bot.send_message(
                    chat_id=config.ADMIN_CHAT_ID,
                    text="🚀 Бот успешно запущен и готов к работе."
                )
            except Exception as e:
                main_logger.warning(f"Could not send message to admin: {e}")

        # Упрощаем запуск приложения
        main_logger.info("Starting bot polling...")
        await bot_manager.application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            close_loop=False  # Важное изменение
        )

    except Exception as e:
        main_logger.error(f"Critical error during bot initialization: {e}")
        raise


def run_bot():
    """Запуск бота с обработкой исключений и правильным закрытием event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Error running bot: {e}")
    finally:
        try:
            loop.stop()
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
        except Exception as e:
            print(f"Error closing loop: {e}")


if __name__ == "__main__":
    run_bot()