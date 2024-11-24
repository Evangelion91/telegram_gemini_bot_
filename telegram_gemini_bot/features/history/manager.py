# C:\Users\gta4r\PycharmProjects\TelegramBot\telegram_gemini_bot\features\history\manager.py
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
import json
import os
import logging
import ijson
from dataclasses import dataclass, asdict


@dataclass
class MessageData:
    """Структура данных сообщения"""
    id: int
    type: str = 'message'
    date: str = ''
    date_unixtime: str = ''
    from_user: str = ''
    from_id: str = ''
    text: str = ''
    is_bot: bool = False
    reply_to_message_id: Optional[int] = None
    entities: List[Dict] = None
    media_type: Optional[str] = None
    media_file_id: Optional[str] = None


class HistoryManager:
    """Менеджер истории сообщений"""

    def __init__(
            self,
            storage_dir: str = "chat_history",
            export_file: str = "chat_export.json",
            max_messages: int = 50,
            logger: Optional[logging.Logger] = None
    ):
        self.storage_dir = storage_dir
        self.export_file = export_file
        self.max_messages = max_messages
        self.logger = logger or logging.getLogger(__name__)

        self.chat_histories: Dict[str, Dict] = {}
        self._ensure_storage_exists()
        self.load_all_histories()

    def _ensure_storage_exists(self) -> None:
        """Создание директории для хранения, если её нет"""
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
            self.logger.info(f"Created storage directory: {self.storage_dir}")

    def _get_chat_file_path(self, chat_id: str) -> str:
        """Получение пути к файлу истории чата"""
        return os.path.join(self.storage_dir, f"chat_{chat_id}.json")

    def load_all_histories(self) -> None:
        """Загрузка всех историй чатов"""
        if not os.path.exists(self.storage_dir):
            return

        for filename in os.listdir(self.storage_dir):
            if filename.startswith("chat_") and filename.endswith(".json"):
                chat_id = filename[5:-5]
                self.load_chat_history(chat_id)

    def load_chat_history(self, chat_id: str) -> None:
        """Загрузка истории конкретного чата"""
        file_path = self._get_chat_file_path(chat_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.chat_histories[chat_id] = json.load(f)
                self.logger.debug(f"Loaded history for chat {chat_id}")
            except json.JSONDecodeError as e:
                self.logger.error(f"Error loading history for chat {chat_id}: {e}")
                self.chat_histories[chat_id] = {'messages': []}

    def save_chat_history(self, chat_id: str) -> None:
        """Сохранение истории чата"""
        if chat_id not in self.chat_histories:
            return

        file_path = self._get_chat_file_path(chat_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.chat_histories[chat_id], f, ensure_ascii=False, indent=2)
            self.logger.debug(f"Saved history for chat {chat_id}")
        except Exception as e:
            self.logger.error(f"Error saving history for chat {chat_id}: {e}")

    def add_message(self, chat_id: str, message_data: Dict[str, Any]) -> None:
        """
        Добавление нового сообщения в историю

        Args:
            chat_id: ID чата
            message_data: Данные сообщения
        """
        if chat_id not in self.chat_histories:
            self.chat_histories[chat_id] = {'messages': []}

        # Создаём структурированное сообщение
        message = MessageData(
            id=message_data.get('message_id', len(self.chat_histories[chat_id]['messages']) + 1),
            date=datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            date_unixtime=str(int(datetime.utcnow().replace(tzinfo=timezone.utc).timestamp())),
            from_user=message_data.get('from_user', {}).get('username', 'Unknown'),
            from_id=f"user{message_data.get('from_user', {}).get('id', 0)}",
            text=message_data.get('text', ''),
            is_bot=message_data.get('from_user', {}).get('is_bot', False),
            reply_to_message_id=message_data.get('reply_to_message_id'),
            entities=message_data.get('entities', []),
            media_type=message_data.get('media_type'),
            media_file_id=message_data.get('media_file_id')
        )

        # Проверяем дубликаты
        messages = self.chat_histories[chat_id]['messages']
        if messages and messages[-1]['text'] == message.text:
            return

        # Добавляем сообщение и ограничиваем количество
        messages.append(asdict(message))
        if len(messages) > self.max_messages:
            messages = messages[-self.max_messages:]

        self.chat_histories[chat_id]['messages'] = messages
        self.save_chat_history(chat_id)

    def get_messages(
            self,
            chat_id: str,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None,
            limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Получение сообщений за период

        Args:
            chat_id: ID чата
            start_time: Начало периода
            end_time: Конец периода
            limit: Ограничение количества сообщений

        Returns:
            List[Dict]: Список сообщений
        """
        messages = []
        export_count = 0

        # Читаем из экспорта если он есть
        if os.path.exists(self.export_file):
            try:
                with open(self.export_file, 'rb') as f:
                    parser = ijson.items(f, 'messages.item')

                    for msg in parser:
                        try:
                            msg_time = datetime.fromtimestamp(
                                int(msg['date_unixtime']),
                                tz=timezone.utc
                            )

                            if ((not start_time or msg_time >= start_time) and
                                    (not end_time or msg_time < end_time)):
                                messages.append(msg)
                                export_count += 1

                        except (KeyError, ValueError) as e:
                            self.logger.error(f"Error processing export message: {e}")
                            continue

            except Exception as e:
                self.logger.error(f"Error reading export: {e}")

        # Добавляем сообщения из текущей истории
        if chat_id in self.chat_histories:
            current_messages = self.chat_histories[chat_id]['messages']
            for msg in current_messages:
                try:
                    msg_time = datetime.fromtimestamp(
                        int(msg['date_unixtime']),
                        tz=timezone.utc
                    )

                    if ((not start_time or msg_time >= start_time) and
                            (not end_time or msg_time < end_time)):
                        messages.append(msg)

                except (KeyError, ValueError) as e:
                    self.logger.error(f"Error processing current message: {e}")
                    continue

        # Сортируем сообщения по времени
        try:
            messages.sort(key=lambda x: int(x['date_unixtime']))
        except Exception as e:
            self.logger.error(f"Error sorting messages: {e}")

        if limit:
            messages = messages[-limit:]

        self.logger.info(
            f"Retrieved {len(messages)} messages\n"
            f"- From export: {export_count}\n"
            f"- Current: {len(messages) - export_count}"
        )

        return messages

    def clear_chat_history(self, chat_id: str) -> None:
        """Очистка истории чата"""
        if chat_id in self.chat_histories:
            self.chat_histories[chat_id]['messages'] = []
            self.save_chat_history(chat_id)
            self.logger.info(f"Cleared history for chat {chat_id}")

    def get_chat_context(
            self,
            chat_id: str,
            message_limit: int = 5
    ) -> List[Dict]:
        """
        Получение контекста чата для генерации ответов

        Args:
            chat_id: ID чата
            message_limit: Количество последних сообщений

        Returns:
            List[Dict]: Список последних сообщений
        """
        if chat_id not in self.chat_histories:
            return []

        messages = self.chat_histories[chat_id]['messages']
        return messages[-message_limit:] if messages else []

    def get_todays_context(self, chat_id: str) -> str:
        """
        Получение и форматирование контекста за текущие сутки

        Args:
            chat_id: ID чата

        Returns:
            str: Отформатированный контекст
        """
        # Получаем начало текущего дня
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Получаем сообщения за сегодня
        messages = self.get_messages(
            chat_id=chat_id,
            start_time=today_start
        )

        if not messages:
            return ""

        # Форматируем сообщения
        formatted_messages = []
        for msg in messages:
            sender = "Бот" if msg.get('is_bot') else msg.get('from_user')
            time = datetime.fromtimestamp(
                int(msg['date_unixtime'])
            ).strftime("%H:%M")
            formatted_messages.append(f"[{time}] {sender}: {msg['text']}")

        return "\n".join(formatted_messages)
