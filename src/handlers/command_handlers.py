from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import logging
from telegram import Update
from telegram.ext import CallbackContext

from src.core.gemini_client import GeminiClient
from src.features.history.manager import HistoryManager
from src.features.summary.generator import SummaryGenerator, SummaryOptions
from src.config import UserStyles


class CommandHandlers:
    """Обработчики команд бота"""

    def __init__(
            self,
            history_manager: HistoryManager,
            gemini_client: GeminiClient,
            logger: Optional[logging.Logger] = None
    ):
        self.history = history_manager
        self.gemini = gemini_client
        self.summary_generator = SummaryGenerator(gemini_client)
        self.logger = logger or logging.getLogger(__name__)

        # Сохраняем маппинг команд для автоматической регистрации
        self.commands = {
            'start': self.handle_start,
            'help': self.handle_help,
            'add_trigger': self.handle_add_trigger,
            'remove_trigger': self.handle_remove_trigger,
            'list_triggers': self.handle_list_triggers,
            'style': self.handle_set_style,
            'set_instructions': self.handle_set_instructions,
            'clear_history': self.handle_clear_history,
            'show_history': self.handle_show_history,
            'summarize_today': self.handle_summarize_today,
            'summarize_hours': self.handle_summarize_hours,
            'summarize_date': self.handle_summarize_date
        }

    async def handle_start(self, update: Update, context: CallbackContext) -> None:
        """Обработка команды /start"""
        triggers = context.chat_data.get('triggers', set())
        welcome_text = (
            "👋 Привет! Я бот для чата с поддержкой Gemini AI.\n\n"
            f"Чтобы обратиться ко мне, используйте одно из слов: {', '.join(sorted(triggers))}\n\n"
            "Доступные команды:\n"
            "/add_trigger - добавить триггерное слово\n"
            "/remove_trigger - удалить триггерное слово\n"
            "/list_triggers - показать список триггеров\n"
            "/style - изменить стиль общения\n"
            "/clear_history - очистить историю сообщений\n"
            "/show_history - показать историю\n"
            "/summarize_today - сводка за сегодня\n"
            "/summarize_hours N - сводка за N часов\n"
            "/summarize_date YYYY-MM-DD - сводка за дату\n"
            "/set_instructions - изменить системные инструкции"
        )
        await update.message.reply_text(welcome_text)

    async def handle_help(self, update: Update, context: CallbackContext) -> None:
        """Обработка команды /help"""
        help_text = (
            "🤖 Справка по использованию бота:\n\n"
            "1. Общение:\n"
            "- Обращайтесь по триггерным словам или в личке\n"
            "- Бот поддерживает контекст беседы\n"
            "- Можно отправлять картинки\n\n"
            "2. Стили общения:\n"
            "- /style - установка стиля\n"
            "- Для разных пользователей свой стиль\n\n"
            "3. История и анализ:\n"
            "- /show_history - просмотр истории\n"
            "- /summarize_today - сводка за день\n"
            "- /summarize_hours N - сводка за период\n"
            "- /summarize_date YYYY-MM-DD - сводка за дату\n\n"
            "4. Настройка:\n"
            "- /add_trigger - добавление триггера\n"
            "- /remove_trigger - удаление триггера\n"
            "- /set_instructions - системные инструкции"
        )
        await update.message.reply_text(help_text)

    async def handle_add_trigger(self, update: Update, context: CallbackContext) -> None:
        """Добавление триггерного слова"""
        if not context.args:
            await update.message.reply_text("ℹ️ Использование: /add_trigger <слово>")
            return

        chat_id = str(update.effective_chat.id)
        trigger = context.args[0].lower()

        if 'triggers' not in context.chat_data:
            context.chat_data['triggers'] = set()

        context.chat_data['triggers'].add(trigger)

        await update.message.reply_text(
            f"✅ Триггер '{trigger}' добавлен\n"
            f"Текущие триггеры: {', '.join(sorted(context.chat_data['triggers']))}"
        )

    async def handle_remove_trigger(self, update: Update, context: CallbackContext) -> None:
        """Удаление триггерного слова"""
        if not context.args:
            await update.message.reply_text("ℹ️ Использование: /remove_trigger <слово>")
            return

        chat_id = str(update.effective_chat.id)
        trigger = context.args[0].lower()

        if 'triggers' in context.chat_data and trigger in context.chat_data['triggers']:
            context.chat_data['triggers'].remove(trigger)
            await update.message.reply_text(
                f"✅ Триггер '{trigger}' удален\n"
                f"Текущие триггеры: {', '.join(sorted(context.chat_data['triggers']))}"
            )
        else:
            await update.message.reply_text(f"❌ Триггер '{trigger}' не найден")

    async def handle_list_triggers(self, update: Update, context: CallbackContext) -> None:
        """Показ списка триггеров"""
        triggers = context.chat_data.get('triggers', set())
        await update.message.reply_text(
            f"📝 Текущие триггеры:\n{', '.join(sorted(triggers))}"
        )

    async def handle_set_style(self, update: Update, context: CallbackContext) -> None:
        """Установка стиля общения"""
        if not context.args:
            current_style = context.chat_data.get('style_prompt', 'стандартный стиль')
            await update.message.reply_text(
                "ℹ️ Использование: /style <описание_стиля>\n"
                f"Текущий стиль: {current_style}"
            )
            return

        new_style = " ".join(context.args)
        context.chat_data['style_prompt'] = new_style
        await update.message.reply_text(f"✅ Установлен новый стиль:\n{new_style}")

    async def handle_set_instructions(self, update: Update, context: CallbackContext) -> None:
        """Установка системных инструкций"""
        if not context.args:
            current_instructions = self.gemini.system_instructions
            await update.message.reply_text(
                "ℹ️ Использование: /set_instructions <инструкции>\n"
                f"Текущие инструкции:\n{current_instructions}"
            )
            return

        new_instructions = " ".join(context.args)
        self.gemini.update_system_instructions(new_instructions)
        await update.message.reply_text("✅ Системные инструкции обновлены")

    async def handle_clear_history(self, update: Update, context: CallbackContext) -> None:
        """Очистка истории"""
        chat_id = str(update.effective_chat.id)
        self.history.clear_chat_history(chat_id)
        await update.message.reply_text("✅ История сообщений очищена")

    async def handle_show_history(self, update: Update, context: CallbackContext) -> None:
        """Показ истории сообщений"""
        chat_id = str(update.effective_chat.id)
        messages = self.history.get_messages(chat_id, limit=10)

        if not messages:
            await update.message.reply_text("📝 История сообщений пуста")
            return

        history_text = "📝 Последние сообщения:\n\n"
        for msg in messages:
            time = datetime.fromtimestamp(int(msg['date_unixtime'])).strftime("%H:%M:%S")
            sender = msg['from_user']
            text = msg['text']
            history_text += f"{time} {sender}:\n{text}\n\n"

        await update.message.reply_text(history_text)

    async def handle_summarize_today(self, update: Update, context: CallbackContext) -> None:
        """Создание сводки за сегодня"""
        chat_id = str(update.effective_chat.id)

        await update.message.reply_text("🤔 Анализирую сообщения за сегодня...")

        # Получаем сообщения за сегодня
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        messages = self.history.get_messages(
            chat_id=chat_id,
            start_time=today
        )

        if not messages:
            await update.message.reply_text("📭 Нет сообщений за сегодня")
            return

        # Получаем стиль пользователя
        username = update.effective_user.username
        user_style = UserStyles.get_style(username)

        # Генерируем сводку
        summary = await self.summary_generator.generate_daily_summary(
            messages=messages,
            style=user_style
        )

        await update.message.reply_text(summary)

    async def handle_summarize_hours(self, update: Update, context: CallbackContext) -> None:
        """Создание сводки за указанное количество часов"""
        if not context.args:
            await update.message.reply_text("ℹ️ Использование: /summarize_hours <количество_часов>")
            return

        try:
            hours = float(context.args[0])
            if hours <= 0:
                raise ValueError("Hours must be positive")

            chat_id = str(update.effective_chat.id)
            await update.message.reply_text(f"🤔 Анализирую сообщения за последние {hours} часов...")

            # Получаем сообщения
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=hours)
            messages = self.history.get_messages(
                chat_id=chat_id,
                start_time=start_time,
                end_time=end_time
            )

            if not messages:
                await update.message.reply_text(f"📭 Нет сообщений за последние {hours} часов")
                return

            # Получаем стиль пользователя
            username = update.effective_user.username
            user_style = UserStyles.get_style(username)

            # Генерируем сводку
            summary = await self.summary_generator.generate_period_summary(
                messages=messages,
                hours=hours,
                style=user_style
            )

            await update.message.reply_text(summary)

        except ValueError:
            await update.message.reply_text("❌ Указано неверное количество часов")
        except Exception as e:
            self.logger.error(f"Error in summarize_hours: {e}")
            await update.message.reply_text("❌ Произошла ошибка при создании сводки")

    async def handle_summarize_date(self, update: Update, context: CallbackContext) -> None:
        """Создание сводки за указанную дату"""
        if not context.args:
            await update.message.reply_text(
                "ℹ️ Использование: /summarize_date YYYY-MM-DD"
            )
            return

        try:
            target_date = datetime.strptime(
                context.args[0], "%Y-%m-%d"
            ).replace(tzinfo=timezone.utc)
            next_date = target_date + timedelta(days=1)

            chat_id = str(update.effective_chat.id)
            await update.message.reply_text(f"🤔 Анализирую сообщения за {context.args[0]}...")

            # Получаем сообщения
            messages = self.history.get_messages(
                chat_id=chat_id,
                start_time=target_date,
                end_time=next_date
            )

            if not messages:
                await update.message.reply_text(f"📭 Нет сообщений за {context.args[0]}")
                return

            # Получаем стиль пользователя
            username = update.effective_user.username
            user_style = UserStyles.get_style(username)

            # Генерируем сводку
            summary = await self.summary_generator.generate_date_summary(
                messages=messages,
                target_date=target_date,
                style=user_style
            )

            await update.message.reply_text(summary)

        except ValueError:
            await update.message.reply_text("❌ Неверный формат даты. Используйте YYYY-MM-DD")
        except Exception as e:
            self.logger.error(f"Error in summarize_date: {e}")
            await update.message.reply_text("❌ Произошла ошибка при создании сводки")