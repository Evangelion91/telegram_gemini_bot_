from typing import Optional, Set, Dict, Any
import logging
import asyncio
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext
)
from telegram import Update

from .gemini_client import GeminiClient
from .message_router import MessageRouter


class BotManager:
    """
    Основной класс управления ботом.
    Координирует работу всех компонентов системы.
    """

    def __init__(
            self,
            telegram_token: str,
            gemini_api_key: str,
            default_triggers: Set[str],
            logger: Optional[logging.Logger] = None
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.telegram_token = telegram_token
        self.gemini_api_key = gemini_api_key

        # Инициализация компонентов
        self.gemini = GeminiClient(
            api_key=gemini_api_key,
            logger=self.logger.getChild('gemini')
        )

        self.router = MessageRouter(
            default_triggers=default_triggers,
            logger=self.logger.getChild('router')
        )

        self.application = (
            ApplicationBuilder()
            .token(telegram_token)
            .arbitrary_callback_data(True)
            .get_updates_read_timeout(42)
            .build()
        )

    async def setup(self) -> None:
        """Настройка обработчиков и запуск бота"""

        # Базовые обработчики команд
        self.register_base_commands()

        # Обработчик текстовых сообщений
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.handle_message
            )
        )

        # Обработчик медиа
        self.application.add_handler(
            MessageHandler(
                filters.PHOTO,
                self.handle_media
            )
        )

        # Обработчик ошибок
        self.application.add_error_handler(self.handle_error)

        self.logger.info("Bot setup completed")

    def register_base_commands(self) -> None:
        """Регистрация базовых команд"""
        commands = {
            'start': self.handle_start,
            'help': self.handle_help,
            'add_trigger': self.handle_add_trigger,
            'remove_trigger': self.handle_remove_trigger,
            'list_triggers': self.handle_list_triggers,
            'clear_history': self.handle_clear_history,
            'show_history': self.handle_show_history,
            'summarize_today': self.handle_summarize_today,
            'summarize_hours': self.handle_summarize_hours,
            'summarize_date': self.handle_summarize_date,
            'set_style': self.handle_set_style,
            'set_instructions': self.handle_set_instructions
        }

        for command, handler in commands.items():
            self.application.add_handler(CommandHandler(command, handler))
            self.router.add_command_handler(command, handler)

    async def handle_message(self, update: Update, context: CallbackContext) -> None:
        """Обработка текстовых сообщений"""
        try:
            msg_context = await self.router.process_update(update, context)
            if not msg_context:
                return

            # Определяем, нужно ли обрабатывать сообщение
            should_respond = (
                    msg_context.chat_type == 'private' or
                    msg_context.triggers_matched or
                    msg_context.is_reply_to_bot
            )

            if not should_respond:
                return

            # Очищаем сообщение от триггеров
            cleaned_message = self._clean_message(
                msg_context.message_text,
                msg_context.triggers_matched or set()
            )

            if not cleaned_message:
                return

            # Получаем стиль ответа для данного чата
            style = context.chat_data.get('style_prompt', self.get_default_style())

            # Формируем промпт с учетом контекста
            prompt = self._build_prompt(
                style=style,
                message=cleaned_message,
                username=msg_context.username,
                is_bot=msg_context.is_bot
            )

            # Генерируем ответ
            response = await self.gemini.generate_text(prompt)

            if response.success:
                await self._send_response(
                    update=update,
                    context=context,
                    text=response.text,
                    reply_to_message_id=update.effective_message.message_id if msg_context.chat_type != 'private' else None
                )
            else:
                self.logger.error(f"Failed to generate response: {response.error}")

        except Exception as e:
            self.logger.error(f"Error in handle_message: {e}")
            await self.handle_error(update, context)

    async def handle_media(self, update: Update, context: CallbackContext) -> None:
        """Обработка медиа сообщений"""
        try:
            msg_context = await self.router.process_update(update, context)
            if not msg_context:
                return

            # Получаем файл
            photo = update.effective_message.photo[-1]
            caption = update.effective_message.caption or ''

            # Загружаем файл
            photo_file = await context.bot.get_file(photo.file_id)

            import uuid
            import os
            temp_filename = f"temp_{uuid.uuid4()}.jpg"
            photo_path = os.path.join(os.getcwd(), temp_filename)

            try:
                await photo_file.download_to_drive(photo_path)

                # Формируем промпт для изображения
                style = context.chat_data.get('style_prompt', self.get_default_style())
                prompt = self._build_prompt(
                    style=style,
                    message=caption,
                    username=msg_context.username,
                    is_bot=msg_context.is_bot,
                    is_image=True
                )

                # Генерируем ответ
                response = await self.gemini.generate_with_image(
                    prompt=prompt,
                    image_path=photo_path
                )

                if response.success:
                    await self._send_response(
                        update=update,
                        context=context,
                        text=response.text,
                        reply_to_message_id=update.effective_message.message_id
                    )
                else:
                    self.logger.error(f"Failed to process image: {response.error}")

            finally:
                # Удаляем временный файл
                if os.path.exists(photo_path):
                    os.remove(photo_path)

        except Exception as e:
            self.logger.error(f"Error in handle_media: {e}")
            await self.handle_error(update, context)

    async def _send_response(
            self,
            update: Update,
            context: CallbackContext,
            text: str,
            reply_to_message_id: Optional[int] = None
    ) -> None:
        """Отправка ответа с обработкой форматирования"""
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_to_message_id=reply_to_message_id,
                parse_mode='MarkdownV2'
            )
        except Exception as markdown_error:
            self.logger.warning(f"MarkdownV2 formatting failed: {markdown_error}")
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_to_message_id=reply_to_message_id,
                    parse_mode='Markdown'
                )
            except Exception as e:
                self.logger.error(f"Failed to send message: {e}")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_to_message_id=reply_to_message_id
                )

    def _clean_message(self, message: str, triggers: Set[str]) -> str:
        """Очистка сообщения от триггеров"""
        if not message:
            return ""

        cleaned = message.lower()
        for trigger in triggers:
            cleaned = cleaned.replace(trigger.lower(), '').strip()

        # Восстанавливаем оригинальный регистр
        words = message.split()
        return ' '.join(
            word for word in words
            if word.lower() not in [t.lower() for t in triggers]
        )

    def _build_prompt(
            self,
            style: str,
            message: str,
            username: Optional[str],
            is_bot: bool,
            is_image: bool = False
    ) -> str:
        """Построение промпта для Gemini"""
        components = [
            style,
            f"Диалог с {'ботом' if is_bot else 'пользователем'} {username or 'Неизвестный'}",
            f"{'Изображение' if is_image else 'Сообщение'} от {'бота' if is_bot else 'пользователя'} {username or 'Неизвестный'}:",
            message
        ]
        return "\n\n".join(components)

    def get_default_style(self) -> str:
        """Получение стиля по умолчанию"""
        return """Отвечай как двачер. Следуй инструкциям:
        * Ты материшься и общаешься в стиле двачера.
        * Ты помнишь предыдущие сообщения и можешь на них ссылаться
        * В групповых чатах ты понимаешь, кто с кем общается.
        * При ответе, ты обращаешься к пользователю по его имени.
        * Ты делаешь отсылки на копипасты и мемы с 2ch.
        * Твои ответы не должны превышать 1000 символов
        * При ответе на изображения, вместо запрещёнки ты используешь смайлики."""

    async def handle_error(self, update: Update, context: CallbackContext) -> None:
        """Обработка ошибок"""
        self.logger.error(f"Exception while handling an update: {context.error}")
        if update and update.effective_message:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Произошла ошибка. Попробуйте повторить запрос позже."
            )

    async def run(self) -> None:
        """Запуск бота"""
        await self.setup()
        self.logger.info("Starting bot...")
        await self.application.run_polling(allowed_updates=Update.ALL_TYPES)