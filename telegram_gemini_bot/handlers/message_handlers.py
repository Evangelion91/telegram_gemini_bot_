from typing import Optional, Dict, Any
import logging
import os
import uuid
from datetime import datetime
from telegram import Update
from telegram.ext import CallbackContext

from telegram_gemini_bot.core.gemini_client import GeminiClient
from telegram_gemini_bot.features.history.manager import HistoryManager
from telegram_gemini_bot.config import UserStyles


class MessageHandlers:
    """Обработчики сообщений"""

    def __init__(
            self,
            history_manager: HistoryManager,
            gemini_client: GeminiClient,
            logger: Optional[logging.Logger] = None
    ):
        self.history = history_manager
        self.gemini = gemini_client
        self.logger = logger or logging.getLogger(__name__)

    def _clean_triggers(self, text: str, triggers: set) -> str:
        """Очистка текста от триггеров"""
        if not text:
            return ""

        cleaned = text.lower()
        for trigger in triggers:
            cleaned = cleaned.replace(trigger.lower(), '').strip()

        words = text.split()
        return ' '.join(
            word for word in words
            if word.lower() not in [t.lower() for t in triggers]
        )

    def _build_prompt(
            self,
            chat_type: str,
            username: str,
            message: str,
            style: Optional[str] = None,
            is_image: bool = False
    ) -> str:
        """Построение промпта с учетом стиля и контекста"""
        components = []

        # Добавляем базовый стиль
        base_style = """Отвечай как двачер. Следуй инструкциям:
                * Ты материшься и общаешься в стиле двачера.
                * Ты помнишь предыдущие сообщения и можешь на них ссылаться
                * В групповых чатах ты понимаешь, кто с кем общается.
                * При ответе, ты обращаешься к пользователю по его имени.
                * Ты делаешь отсылки на копипасты и мемы с 2ch.
                * Твои ответы не должны превышать 1000 символов
                * При ответе на изображения, вместо запрещёнки ты используешь смайлики."""
        components.append(style or base_style)

        # Добавляем специфичный стиль для пользователя
        user_style = UserStyles.get_style(username)
        if user_style:
            components.append(f"Для пользователя {username}: {user_style}")

        # Добавляем контекст сообщения
        msg_type = "Изображение" if is_image else "Сообщение"
        components.append(f"Тип чата: {chat_type}")
        components.append(f"{msg_type} от пользователя {username}:\n{message}")

        return "\n\n".join(components)

    async def handle_text_message(self, update: Update, context: CallbackContext) -> None:
        """Обработка текстовых сообщений"""
        message = update.effective_message
        chat_id = str(update.effective_chat.id)

        if not message or not message.text:
            return

        try:
            # Сохраняем сообщение в историю
            self.history.add_message(chat_id, {
                'message_id': message.message_id,
                'from_user': message.from_user.to_dict() if message.from_user else {},
                'text': message.text,
                'entities': [e.to_dict() for e in (message.entities or [])]
            })

            # Проверяем триггеры и формируем ответ
            triggers = context.chat_data.get('triggers', set())
            cleaned_message = self._clean_triggers(message.text, triggers)

            if not cleaned_message:
                return

            # Формируем промпт
            prompt = self._build_prompt(
                chat_type=update.effective_chat.type,
                username=message.from_user.username if message.from_user else "Unknown",
                message=cleaned_message,
                style=context.chat_data.get('style_prompt')
            )

            # Генерируем ответ
            response = await self.gemini.generate_text(prompt)

            if response.success and response.text:
                # Сохраняем ответ в историю
                self.history.add_message(chat_id, {
                    'message_id': message.message_id + 1,
                    'from_user': {
                        'id': context.bot.id,
                        'username': context.bot.username,
                        'is_bot': True
                    },
                    'text': response.text
                })

                # Отправляем ответ
                try:
                    await update.effective_message.reply_text(
                        response.text,
                        parse_mode='MarkdownV2'
                    )
                except Exception:
                    try:
                        await update.effective_message.reply_text(
                            response.text,
                            parse_mode='Markdown'
                        )
                    except Exception:
                        await update.effective_message.reply_text(response.text)

        except Exception as e:
            self.logger.error(f"Error handling text message: {e}")
            await update.effective_message.reply_text("❌ Произошла ошибка. Попробуйте повторить запрос.")

    async def handle_image_message(self, update: Update, context: CallbackContext) -> None:
        """Обработка сообщений с изображениями"""
        message = update.effective_message
        chat_id = str(update.effective_chat.id)

        if not message or not message.photo:
            return

        try:
            # Сохраняем сообщение в историю
            self.history.add_message(chat_id, {
                'message_id': message.message_id,
                'from_user': message.from_user.to_dict() if message.from_user else {},
                'text': f"[Изображение]{' с подписью: ' + message.caption if message.caption else ''}",
                'media_type': 'photo',
                'media_file_id': message.photo[-1].file_id
            })

            # Загружаем изображение
            photo = message.photo[-1]
            photo_file = await context.bot.get_file(photo.file_id)

            temp_filename = f"temp_{uuid.uuid4()}.jpg"
            photo_path = os.path.join(os.getcwd(), temp_filename)

            try:
                await photo_file.download_to_drive(photo_path)

                # Формируем промпт
                prompt = self._build_prompt(
                    chat_type=update.effective_chat.type,
                    username=message.from_user.username if message.from_user else "Unknown",
                    message=message.caption or "",
                    style=context.chat_data.get('style_prompt'),
                    is_image=True
                )

                # Генерируем ответ
                response = await self.gemini.generate_with_image(
                    prompt=prompt,
                    image_path=photo_path
                )

                if response.success and response.text:
                    # Сохраняем ответ в историю
                    self.history.add_message(chat_id, {
                        'message_id': message.message_id + 1,
                        'from_user': {
                            'id': context.bot.id,
                            'username': context.bot.username,
                            'is_bot': True
                        },
                        'text': response.text
                    })

                    # Отправляем ответ
                    try:
                        await update.effective_message.reply_text(
                            response.text,
                            parse_mode='MarkdownV2'
                        )
                    except Exception:
                        try:
                            await update.effective_message.reply_text(
                                response.text,
                                parse_mode='Markdown'
                            )
                        except Exception:
                            await update.effective_message.reply_text(response.text)

            finally:
                # Удаляем временный файл
                if os.path.exists(photo_path):
                    os.remove(photo_path)

        except Exception as e:
            self.logger.error(f"Error handling image message: {e}")
            await update.effective_message.reply_text(
                "❌ Произошла ошибка при обработке изображения."
            )

    async def handle_new_chat_members(self, update: Update, context: CallbackContext) -> None:
        """Обработка новых участников чата"""
        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                await update.message.reply_text(
                    "👋 Привет! Я бот с поддержкой Gemini AI.\n"
                    "Используйте /help для получения справки."
                )
