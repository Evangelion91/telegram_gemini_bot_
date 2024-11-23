from typing import Dict, Set, Optional, Any, Callable, List, Awaitable
import logging
from dataclasses import dataclass
from telegram import Update
from telegram.ext import CallbackContext


@dataclass
class MessageContext:
    """Контекст сообщения для маршрутизации"""
    update: Update
    context: CallbackContext
    chat_id: str
    user_id: str
    username: Optional[str]
    message_text: Optional[str]
    is_bot: bool
    chat_type: str
    is_reply_to_bot: bool = False
    is_command: bool = False
    command_args: List[str] = None
    triggers_matched: Set[str] = None


class MessageRouter:
    """
    Маршрутизатор сообщений.
    Определяет как должно быть обработано входящее сообщение.
    """

    def __init__(
            self,
            default_triggers: Set[str],
            logger: Optional[logging.Logger] = None
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.default_triggers = default_triggers
        self.chat_triggers: Dict[str, Set[str]] = {}
        self.command_handlers: Dict[str, Callable] = {}
        self.message_handlers: List[Callable] = []

    async def process_update(
            self,
            update: Update,
            context: CallbackContext
    ) -> Optional[MessageContext]:
        """
        Обработка входящего обновления

        Args:
            update: Входящее обновление
            context: Контекст callback'а

        Returns:
            MessageContext: Контекст сообщения или None
        """
        if not update.effective_message:
            return None

        message = update.effective_message
        chat_id = str(update.effective_chat.id)

        # Базовая информация
        msg_context = MessageContext(
            update=update,
            context=context,
            chat_id=chat_id,
            user_id=str(message.from_user.id) if message.from_user else None,
            username=message.from_user.username if message.from_user else None,
            message_text=message.text,
            is_bot=message.from_user.is_bot if message.from_user else False,
            chat_type=update.effective_chat.type,
            command_args=[]
        )

        # Проверка на команду
        if message.text and message.text.startswith('/'):
            command_parts = message.text[1:].split()
            command = command_parts[0].lower()
            msg_context.is_command = True
            msg_context.command_args = command_parts[1:]

            if command in self.command_handlers:
                await self.command_handlers[command](update, context)
                return msg_context

        # Проверка триггеров
        if message.text:
            triggers = self.chat_triggers.get(chat_id, self.default_triggers)
            matched_triggers = {
                trigger for trigger in triggers
                if trigger.lower() in message.text.lower()
            }

            if matched_triggers:
                msg_context.triggers_matched = matched_triggers

        # Проверка ответа на сообщение бота
        if (message.reply_to_message and
                message.reply_to_message.from_user and
                message.reply_to_message.from_user.id == context.bot.id):
            msg_context.is_reply_to_bot = True

        return msg_context

    def add_command_handler(
            self,
            command: str,
            handler: Callable[[Update, CallbackContext], Awaitable[Any]]
    ) -> None:
        """Добавление обработчика команды"""
        self.command_handlers[command.lower()] = handler
        self.logger.debug(f"Added command handler for /{command}")

    def add_message_handler(
            self,
            handler: Callable[[Update, CallbackContext], Awaitable[Any]]
    ) -> None:
        """Добавление обработчика сообщений"""
        self.message_handlers.append(handler)
        self.logger.debug("Added message handler")

    def add_chat_trigger(self, chat_id: str, trigger: str) -> None:
        """Добавление триггера для конкретного чата"""
        if chat_id not in self.chat_triggers:
            self.chat_triggers[chat_id] = set(self.default_triggers)
        self.chat_triggers[chat_id].add(trigger.lower())

    def remove_chat_trigger(self, chat_id: str, trigger: str) -> bool:
        """Удаление триггера для конкретного чата"""
        if chat_id in self.chat_triggers:
            trigger = trigger.lower()
            if trigger in self.chat_triggers[chat_id]:
                self.chat_triggers[chat_id].remove(trigger)
                return True
        return False

    def get_chat_triggers(self, chat_id: str) -> Set[str]:
        """Получение списка триггеров для чата"""
        return self.chat_triggers.get(chat_id, self.default_triggers)