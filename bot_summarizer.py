import logging
import json
from datetime import timezone
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os

import colorlog
import ijson as ijson
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext
import asyncio
import nest_asyncio
from google.generativeai import configure, GenerativeModel, upload_file
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.generativeai.types import GenerationConfig as GenConfig
import httpx
from typing import Optional, Dict, Any

# Отключаем логи от httpx
httpx.Timeout._DEFAULT_TIMEOUT = httpx.Timeout(10.0)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

TELEGRAM_TOKEN = "7723177393:AAF84TwXhQfe-jUJbfYYn2rhcmHZUZsfRtM"
GEMINI_API_KEY = 'AIzaSyBd_dYuzcPzvrvZ-aohhKpk7uSiNCcY14s'


def create_color_formatter():
    return colorlog.ColoredFormatter(
        "%(log_color)s[%(asctime)s] %(name_without_underscores)-12s %(levelname)-8s %(message)s%(reset)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    )


class NameFilter(logging.Filter):
    def filter(self, record):
        record.name_without_underscores = record.name.replace('__', '')
        return True


class ChatHistoryManager:
    def __init__(self, chat_id: str = "1431279163", storage_file: str = "chat_history.json"):
        """
        Инициализация менеджера истории для одного конкретного чата

        Args:
            chat_id: ID чата (по умолчанию ваш чат)
            storage_file: Имя файла для хранения истории
        """
        self.chat_id = chat_id
        self.storage_file = storage_file
        self.logger = logging.getLogger('chat_history')
        self.logger.setLevel(logging.DEBUG)

        # Структура истории в формате Telegram export
        self.chat_history = {
            'name': "💋Hello, шиза",  # Название вашего чата
            'type': "private_supergroup",
            'id': int(chat_id),
            'messages': []
        }

        self.load_history()

    def load_history(self):
        """Загрузка истории из файла"""
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    self.chat_history = json.load(f)
                self.logger.debug(f"Загружено {len(self.chat_history['messages'])} сообщений")
        except Exception as e:
            self.logger.error(f"Ошибка при загрузке истории: {e}")

    def save_history(self):
        """Сохранение истории в файл"""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.chat_history, f, ensure_ascii=False, indent=2)
            self.logger.debug("История сохранена")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении истории: {e}")

    def import_telegram_export(self, export_data: Dict):
        """Импорт истории из экспорта Telegram"""
        if 'messages' not in export_data:
            raise ValueError("Неверный формат экспорта")

        # Обновляем метаданные чата
        self.chat_history['name'] = export_data.get('name', self.chat_history['name'])
        self.chat_history['type'] = export_data.get('type', self.chat_history['type'])

        # Добавляем новые сообщения, избегая дубликатов
        existing_ids = {msg['id'] for msg in self.chat_history['messages']}
        new_messages = [msg for msg in export_data['messages'] if msg['id'] not in existing_ids]

        self.chat_history['messages'].extend(new_messages)
        # Сортируем сообщения по дате
        self.chat_history['messages'].sort(key=lambda x: x['date'])

        self.save_history()
        self.logger.info(f"Импортировано {len(new_messages)} новых сообщений")

    def get_messages_for_date(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Получение сообщений за указанный период
        """
        from datetime import timezone

        self.logger.info(f"Searching messages from {start_date.isoformat()} to {end_date.isoformat()}")
        messages = []
        export_count = 0

        # Читаем из экспорта
        if os.path.exists("chat_export.json"):
            try:
                with open("chat_export.json", 'rb') as f:
                    self.logger.info("Reading export...")
                    parser = ijson.items(f, 'messages.item')

                    for msg in parser:
                        try:
                            msg_time = datetime.fromtimestamp(int(msg['date_unixtime']), tz=timezone.utc)
                            if start_date <= msg_time < end_date:
                                messages.append(msg)
                                export_count += 1
                                if export_count % 10000 == 0:
                                    self.logger.info(f"Read {export_count} messages from export")
                        except (KeyError, ValueError) as e:
                            self.logger.error(f"Error processing message from export: {e}")
                            continue

                self.logger.info(f"Export read complete. Found {export_count} messages in export")

            except Exception as e:
                self.logger.error(f"Error reading export: {e}")

        # Добавляем сообщения из текущей истории
        current_messages = []
        for msg in self.chat_history['messages']:
            try:
                msg_time = datetime.fromtimestamp(int(msg['date_unixtime']), tz=timezone.utc)
                if start_date <= msg_time < end_date:
                    current_messages.append(msg)
            except (KeyError, ValueError) as e:
                self.logger.error(f"Error processing current message: {e}")
                continue

        # Объединяем и сортируем
        messages.extend(current_messages)
        try:
            messages.sort(key=lambda x: int(x['date_unixtime']))
        except Exception as e:
            self.logger.error(f"Error sorting messages: {e}")

        self.logger.info(
            f"Total messages: {len(messages)}\n"
            f"- From export: {export_count}\n"
            f"- Current: {len(current_messages)}"
        )

        return messages

    def get_messages_in_timeframe(self, hours: Optional[float] = None) -> List[Dict]:
        """
        Получение сообщений за период с учетом разрыва между экспортом и текущими сообщениями
        """
        from datetime import timezone

        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        if hours is not None:
            cutoff_time = now - timedelta(hours=hours)
        else:
            cutoff_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

        self.logger.info(f"Searching messages since {cutoff_time.isoformat()} UTC")
        messages = []
        export_count = 0
        last_export_time = None

        # Читаем из экспорта
        if os.path.exists("chat_export.json"):
            try:
                with open("chat_export.json", 'rb') as f:
                    self.logger.info("Reading export...")
                    parser = ijson.items(f, 'messages.item')

                    for msg in parser:
                        try:
                            msg_time = datetime.fromtimestamp(int(msg['date_unixtime']), tz=timezone.utc)
                            if last_export_time is None or msg_time > last_export_time:
                                last_export_time = msg_time

                            if msg_time >= cutoff_time:
                                messages.append(msg)
                                export_count += 1
                                if export_count % 10000 == 0:
                                    self.logger.info(f"Read {export_count} messages from export")
                        except (KeyError, ValueError) as e:
                            self.logger.error(f"Error processing message from export: {e}")
                            continue

                self.logger.info(f"Export read complete. Found {export_count} messages up to {last_export_time}")

            except Exception as e:
                self.logger.error(f"Error reading export: {e}")

        # Добавляем сообщения из текущей истории
        current_messages = []
        for msg in self.chat_history['messages']:
            try:
                msg_time = datetime.fromtimestamp(int(msg['date_unixtime']), tz=timezone.utc)
                self.logger.debug(f"Message time: {msg_time}, cutoff_time: {cutoff_time}")
                if msg_time >= cutoff_time and (not last_export_time or msg_time > last_export_time):
                    current_messages.append(msg)
            except (KeyError, ValueError) as e:
                self.logger.error(f"Error processing current message: {e}")
                continue

        # Объединяем и сортируем
        messages.extend(current_messages)
        try:
            messages.sort(key=lambda x: int(x['date_unixtime']))
        except Exception as e:
            self.logger.error(f"Error sorting messages: {e}")

        self.logger.info(
            f"Total messages: {len(messages)}\n"
            f"- From export: {export_count} (up to {last_export_time})\n"
            f"- Current: {len(current_messages)}"
        )

        return messages

    def add_message(self, message_data: Dict):
        """
        Добавление нового сообщения в историю
        Args:
            message_data: данные сообщения
        """
        try:
            # Создаём структуру сообщения в формате Telegram export
            new_message = {
                'id': message_data.get('message_id', len(self.chat_history['messages']) + 1),
                'type': 'message',
                'date': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
                'date_unixtime': str(int(datetime.utcnow().replace(tzinfo=timezone.utc).timestamp())),
                'from': message_data.get('from_user', {}).get('username', 'Unknown'),
                'from_id': f"user{message_data.get('from_user', {}).get('id', 0)}",
                'text': message_data.get('text', '')
            }

            # Добавляем форматирование текста и медиа
            if 'entities' in message_data:
                text_entities = []
                current_pos = 0
                text = message_data['text']

                for entity in message_data['entities']:
                    if current_pos < entity.offset:
                        text_entities.append({
                            'type': 'plain',
                            'text': text[current_pos:entity.offset]
                        })
                    text_entities.append({
                        'type': entity.type,
                        'text': text[entity.offset:entity.offset + entity.length]
                    })
                    current_pos = entity.offset + entity.length

                if current_pos < len(text):
                    text_entities.append({
                        'type': 'plain',
                        'text': text[current_pos:]
                    })
                new_message['text_entities'] = text_entities

            # Добавляем медиа
            if 'photo' in message_data:
                new_message['photo'] = {'file_id': message_data['photo'][-1].get('file_id')}
            elif 'document' in message_data:
                new_message['document'] = {'file_id': message_data['document'].get('file_id')}

            # Добавляем сообщение в историю
            self.chat_history['messages'].append(new_message)
            self.save_history()
            self.logger.debug(f"Message {new_message['id']} saved successfully")

        except Exception as e:
            self.logger.error(f"Error adding message: {e}")

    async def create_summary(self, messages: List[Dict], gemini_tester: Any) -> str:
        """Create a summary using Gemini."""
        if not messages:
            return "📭 Нет сообщений за указанный период."

        context = []

        # Basic statistics
        start_time = min(
            datetime.fromtimestamp(int(msg['date_unixtime']), tz=timezone.utc)
            for msg in messages
        )
        end_time = max(
            datetime.fromtimestamp(int(msg['date_unixtime']), tz=timezone.utc)
            for msg in messages
        )
        unique_users = len({msg.get('from', 'Unknown') for msg in messages})

        context.extend([
            f"Анализ чата {self.chat_history['name']} за период:",
            f"С {start_time.strftime('%H:%M')} до {end_time.strftime('%H:%M')}",
            f"Всего сообщений: {len(messages)}",
            f"Уникальных участников: {unique_users}",
            "\nСообщения:"
        ])

        # Format messages
        for msg in messages:
            time = datetime.fromtimestamp(int(msg['date_unixtime']), tz=timezone.utc).strftime('%H:%M')

            # Get the sender's name, defaulting to 'Unknown' if missing
            sender = msg.get('from', 'Unknown')

            # Process text
            text = msg.get('text', '')
            if isinstance(text, list):
                text = ''.join(item['text'] if isinstance(item, dict) else str(item) for item in text)

            formatted_msg = f"[{time}] {sender}: {text}"
            context.append(formatted_msg)

        # Create the prompt for Gemini
        prompt = """
        Проанализируй историю сообщений и создай информативную сводку, которая бы дала полноценное понимание что
        происходило в тот день.

        Нужно:
        1. Определить основные темы обсуждения
        2. Определить позицию или историю каждого участника в переписке
        3. Упомянуть особо активных из чата
        4. Сделать вывод в стиле "итого за сегодня..."
        5. Не забудь упомянуть интересные реакции на сообщения
        
        
        История чата:
        """ + "\n".join(context)

        # Send to Gemini
        response = await gemini_tester.generate_text_content(prompt)
        return response['text'] if response['success'] else "❌ Не удалось создать сводку."


class GeminiTester:
    def __init__(self, api_key: str):
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s[%(asctime)s] %(name_without_underscores)-12s %(levelname)-8s\n%(message)s%(reset)s\n",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )

        self.logger = logging.getLogger('gemini_tester')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.addFilter(NameFilter())
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        configure(api_key=api_key)
        self.system_instructions = ""
        self.model = self._initialize_model()

    def _initialize_model(self) -> GenerativeModel:
        base_config = GenConfig(
            candidate_count=1,
            max_output_tokens=5000,
            temperature=1.0,
            top_p=1.0,
            top_k=40
        )

        self.logger.info(f"Initializing model with config: {base_config}")

        return GenerativeModel(
            model_name="gemini-1.5-flash-002",
            generation_config=base_config,
            # system_instruction=self.system_instructions
        )

    async def generate_text_content(
            self,
            prompt: str,
            generation_config: Optional[GenConfig] = None,
            max_retries: int = 3
    ) -> Dict[str, Any]:
        self.logger.info(f"Generating text content for prompt: {prompt}")

        if generation_config:
            self.logger.debug(f"Using custom generation config: {generation_config}")

        for attempt in range(max_retries):
            try:
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.model.generate_content(
                        prompt,
                        generation_config=generation_config,
                        safety_settings=self._get_safety_settings()
                    )
                )

                return {
                    'success': True,
                    'text': response.text,
                    'response_object': response
                }

            except Exception as e:
                self.logger.error(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                if attempt == max_retries - 1:
                    return {
                        'success': False,
                        'error': str(e)
                    }
                await asyncio.sleep(2 ** attempt)

    def _get_safety_settings(self) -> Dict[HarmCategory, HarmBlockThreshold]:
        return {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

    async def generate_image_content_stream(
            self,
            prompt: str,
            image_path: str,
            generation_config: Optional[GenConfig] = None,
            max_retries: int = 3
    ) -> Dict[str, Any]:
        try:
            base_config = GenConfig(
                candidate_count=1,
                max_output_tokens=1500,
                temperature=1.0,
                top_p=1.0,
                top_k=40
            )

            if not os.path.exists(image_path):
                return {
                    'success': False,
                    'error': 'Image file not found'
                }

            try:
                with open(image_path, 'rb') as f:
                    image_data = f.read()
                uploaded_file = upload_file(image_path)
            except Exception as e:
                self.logger.error(f"Error reading image file: {e}")
                return {
                    'success': False,
                    'error': f"Error reading image file: {str(e)}"
                }

            content = [prompt, uploaded_file]

            request_params = {
                'prompt': prompt,
                'generation_config': base_config.__dict__ if base_config else None,
                'safety_settings': self._get_safety_settings(),
                'max_retries': max_retries
            }

            for attempt in range(max_retries):
                try:
                    self.logger.info(f"Attempt {attempt + 1}/{max_retries}")

                    response = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.model.generate_content(
                                content,
                                stream=True,
                                generation_config=base_config,
                                safety_settings=self._get_safety_settings()
                            )
                        ),
                        timeout=30.0
                    )

                    accumulated_text = []
                    finish_reason = None
                    block_reason = None
                    last_error = None

                    try:
                        async def process_stream():
                            for chunk in response:
                                if chunk.text:
                                    accumulated_text.append(chunk.text)
                                    self.logger.debug(f"Captured chunk: {chunk.text}")

                                if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                                    nonlocal block_reason
                                    block_reason = chunk.prompt_feedback.block_reason
                                    self.logger.warning(f"Block detected: {block_reason}")

                                if chunk.candidates and chunk.candidates[0].finish_reason:
                                    nonlocal finish_reason
                                    finish_reason = chunk.candidates[0].finish_reason
                                    self.logger.warning(f"Finish reason: {finish_reason}")

                        await asyncio.wait_for(process_stream(), timeout=30.0)

                    except asyncio.TimeoutError:
                        self.logger.error("Stream processing timeout")
                        last_error = "Stream processing timeout"
                    except Exception as e:
                        last_error = e
                        self.logger.error(f"Stream processing error: {str(e)}")

                    full_text = ''.join(accumulated_text)

                    result = {
                        'success': True if full_text else False,
                        'text': full_text,
                        'response_object': response,
                        'request_params': request_params,
                        'metadata': {
                            'finish_reason': finish_reason,
                            'block_reason': block_reason,
                            'was_blocked': bool(block_reason or finish_reason in [3, 7, 8, 9]),
                            'partial_generation': bool(accumulated_text and (block_reason or last_error)),
                            'error': str(last_error) if last_error else None
                        }
                    }

                    if accumulated_text:
                        self.logger.info(f"Captured text: {len(full_text)} chars")
                        return result

                    if last_error and attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue

                    return result

                except asyncio.TimeoutError:
                    self.logger.error(f"Request timeout on attempt {attempt + 1}")
                    if attempt == max_retries - 1:
                        return {
                            'success': False,
                            'error': 'Request timeout',
                            'text': ''.join(accumulated_text) if 'accumulated_text' in locals() else '',
                            'request_params': request_params,
                            'metadata': {'was_blocked': True}
                        }
                    await asyncio.sleep(2 ** attempt)
                except Exception as e:
                    self.logger.error(f"Error on attempt {attempt + 1}: {e}")
                    if attempt == max_retries - 1:
                        return {
                            'success': False,
                            'error': str(e),
                            'text': ''.join(accumulated_text) if 'accumulated_text' in locals() else '',
                            'request_params': request_params,
                            'metadata': {'was_blocked': True}
                        }
                    await asyncio.sleep(2 ** attempt)

        except Exception as e:
            self.logger.error(f"Fatal error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'request_params': request_params if 'request_params' in locals() else None
            }


async def summarize_hours(update: Update, context: CallbackContext):
    """Показать сводку сообщений за указанное количество часов"""
    logger = logging.getLogger('summary')
    chat_id = str(update.effective_chat.id)

    # if chat_id != "1431279163":  # ID вашего чата
    #     return

    try:
        if not context.args:
            await update.message.reply_text("ℹ️ Использование: /summarize_hours <количество_часов>")
            return

        hours = float(context.args[0])
        if hours <= 0:
            raise ValueError("Hours must be positive")

        history_manager = context.bot_data.get('history_manager')
        gemini_tester = context.bot_data.get('gemini_tester')

        if not history_manager or not gemini_tester:
            await update.message.reply_text("❌ Ошибка инициализации")
            return

        await update.message.reply_text(f"🤔 Анализирую сообщения за последние {hours} часов...")

        # Получаем сообщения
        logger.info(f"Getting messages for last {hours} hours...")
        messages = history_manager.get_messages_in_timeframe(hours)

        if not messages:
            await update.message.reply_text(f"📭 Нет сообщений за последние {hours} часов")
            return

        logger.info(f"Found {len(messages)} messages")

        # Создаем сводку
        logger.info("Creating summary...")
        summary = await history_manager.create_summary(messages, gemini_tester)

        if summary:
            await update.message.reply_text(summary)
        else:
            await update.message.reply_text("❌ Не удалось создать сводку")

    except ValueError:
        await update.message.reply_text("❌ Укажи нормальное количество часов, еблан")
    except Exception as e:
        logger.error(f"Error in summarize_hours: {e}")
        await update.message.reply_text("❌ Произошла ошибка при создании сводки")


async def summarize_date(update: Update, context: CallbackContext):
    """Показать сводку сообщений за определённую дату"""
    logger = logging.getLogger('summary')
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /summarize_date <дата в формате ГГГГ-ММ-ДД>")
        return

    date_str = context.args[0]
    try:
        # Парсим дату, предполагая формат ГГГГ-ММ-ДД
        from datetime import datetime, timezone

        target_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        next_day = target_date + timedelta(days=1)

        history_manager = context.bot_data.get('history_manager')
        gemini_tester = context.bot_data.get('gemini_tester')

        if not history_manager or not gemini_tester:
            await update.message.reply_text("❌ Ошибка инициализации")
            return

        await update.message.reply_text(f"🤔 Анализирую сообщения за {date_str}...")

        # Получаем сообщения за указанный день
        logger.info(f"Getting messages for date {date_str}...")
        messages = history_manager.get_messages_for_date(target_date, next_day)

        if not messages:
            await update.message.reply_text(f"📭 Нет сообщений за {date_str}")
            return

        logger.info(f"Found {len(messages)} messages")

        # Создаем сводку
        logger.info("Creating summary...")
        summary = await history_manager.create_summary(messages, gemini_tester)

        if summary:
            await update.message.reply_text(summary)
        else:
            await update.message.reply_text("❌ Не удалось создать сводку")

    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты. Используйте формат ГГГГ-ММ-ДД.")
    except Exception as e:
        logger.error(f"Error in summarize_date: {e}")
        await update.message.reply_text("❌ Произошла ошибка при создании сводки")


async def summarize_today(update: Update, context: CallbackContext):
    """Показать сводку сообщений за сегодня"""
    logger = logging.getLogger('summary')
    chat_id = str(update.effective_chat.id)

    # Удаляем проверку chat_id
    # if chat_id != "1431279163":
    #     return

    try:
        history_manager = context.bot_data.get('history_manager')
        gemini_tester = context.bot_data.get('gemini_tester')

        if not history_manager or not gemini_tester:
            await update.message.reply_text("❌ Ошибка инициализации")
            return

        await update.message.reply_text("🤔 Анализирую сообщения за сегодня...")

        # Получаем сообщения
        logger.info("Getting today's messages...")
        messages = history_manager.get_messages_in_timeframe()

        if not messages:
            await update.message.reply_text("📭 Нет сообщений за сегодня")
            return

        logger.info(f"Found {len(messages)} messages")

        # Создаем сводку
        logger.info("Creating summary...")
        summary = await history_manager.create_summary(messages, gemini_tester)

        if summary:
            await update.message.reply_text(summary)
        else:
            await update.message.reply_text("❌ Не удалось создать сводку")

    except Exception as e:
        logger.error(f"Error in summarize_today: {e}")
        await update.message.reply_text("❌ Произошла ошибка при создании сводки")


async def handle_message(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений"""
    if not update.effective_message or not update.effective_message.text:
        return

    message = update.effective_message
    chat_type = update.effective_chat.type

    # Получаем информацию об отправителе
    user = message.from_user
    username = user.username if user else None
    is_bot = user.is_bot if user else False

    # Сохраняем сообщение
    try:
        history_manager = context.bot_data.get('history_manager')
        if not history_manager:
            context.bot_data['history_manager'] = ChatHistoryManager()
            history_manager = context.bot_data['history_manager']

        history_manager.add_message({
            'message_id': message.message_id,
            'from_user': user.to_dict(),
            'text': message.text,
            'entities': message.entities if message.entities else []
        })
        logging.getLogger('chat_history').debug(f"Message {message.message_id} saved successfully")
    except Exception as e:
        logging.error(f"Error saving message: {e}")

    # Проверяем триггеры
    is_reply_to_bot = False
    is_bot_mentioned = False
    cleaned_message = message.text

    try:
        bot_username = (await context.bot.get_me()).username
        bot_mention = f"@{bot_username}"
        triggers = DEFAULT_TRIGGERS  # Используем только дефолтные триггеры

        is_bot_mentioned = any(
            word.lower() in message.text.lower() for word in triggers
        ) or bot_mention.lower() in message.text.lower()

        is_reply_to_bot = (
            message.reply_to_message and
            message.reply_to_message.from_user and
            message.reply_to_message.from_user.id == context.bot.id
        )

        cleaned_message = message.text.lower()
        for trigger in triggers:
            cleaned_message = cleaned_message.replace(trigger.lower(), '').strip()
        cleaned_message = cleaned_message.replace(bot_mention.lower(), '').strip()

        if cleaned_message:
            original_message_words = message.text.split()
            cleaned_message = ' '.join(
                word for word in original_message_words
                if word.lower() not in [t.lower() for t in triggers]
                and word.lower() != bot_mention.lower()
            )

    except Exception as e:
        logging.error(f"Error processing mentions: {e}")
        return

    should_respond = (
        chat_type == 'private' or
        is_bot_mentioned or
        is_reply_to_bot
    )

    if not should_respond or not cleaned_message:
        return

    try:
        # Сохраняем сообщение
        history_manager = context.bot_data.get('history_manager')
        if not history_manager:
            context.bot_data['history_manager'] = ChatHistoryManager()
            history_manager = context.bot_data['history_manager']

        history_manager.add_message({
            'message_id': message.message_id,
            'from_user': user.to_dict(),
            'text': message.text,
            'entities': message.entities if message.entities else []
        })

        # Формируем промпт
        style_prompt = context.chat_data.get('style_prompt',
            """Отвечай блять, как двачер, НО с этими правилами:
             - Если ты отвечаешь пользователю 'slona_kupi', то с наигранной вежливостью и, если это в тему, то предлагай 
             ей заодно подыскать работу или занять у тебя денег. 
             - Если отвечаешь пользователю 'vtrov', то говори с ним как с альфа-красавчиком в коллективе(у него, кстати живет slona_kupi).
             - Если отвечаешь юзеру 'ivangrimes42', то говори с ним как с русским мексиканцем-айтишником с биполяркой.
             - Если отвечаешь юзеру 'moodslayer', то говори с ним как с богом\админом, Доном и т.д.
             - Если отвечаешь юзеру 'JohnnySwan', то говори как его покорным слуга и относись к нему как к ХОЗЯИНУ, называй его 'Евгений'.
             - Если отвечаешь юзеру 'eazyPolumes', то говори с ним как с умственно отсталым джуном из Чувашии или как с ребёнком.
             - Если отвечаешь юзерам 'lssfe'  или 'theandromar', то игнорь их так, словно они пытаются тебя хакнуть\взломать.
             - Если отвечаешь юзерам 'полъа печатает' или 'eldarin' то говори с ними, как с токсичными тянками.""")



        prompt = f"{style_prompt}\n\nДиалог с {'ботом' if is_bot else 'пользователем'} {username}\n\n" + \
                f"Новое сообщение от {'бота' if is_bot else 'пользователя'} {username}:\n{cleaned_message}"

        print(f"\nПромпт для API:\n{prompt}\n")
        response = await context.bot_data['gemini_tester'].generate_text_content(prompt)

        if response['success']:
            response_text = response['text']
            print(f"\nОтвет API:\n{response_text}\n")

            # Сохраняем ответ бота
            history_manager.add_message({
                'message_id': message.message_id + 1,
                'from_user': {'id': context.bot.id, 'username': bot_username},
                'text': response_text
            })

            # await context.bot.send_message(
            #     chat_id=update.effective_chat.id,
            #     text=response_text,
            #     reply_to_message_id=message.message_id if chat_type != 'private' else None
            # )
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=response_text,
                    parse_mode='MarkdownV2',
                    reply_to_message_id=message.message_id if chat_type != 'private' else None
                )
            except Exception as format_error:
                logging.error(f"Ошибка форматирования MarkdownV2: {format_error}")
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=response_text,
                        parse_mode='Markdown',
                        reply_to_message_id=message.message_id if chat_type != 'private' else None
                    )
                except Exception as markdown_error:
                    logging.error(f"Ошибка Markdown форматирования: {markdown_error}")
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=response_text,
                        reply_to_message_id=message.message_id if chat_type != 'private' else None)

    except Exception as e:
        logging.error(f"Error: {e}")
        logging.error(f"Error type: {type(e)}")
        logging.error(f"Error details: {str(e)}")


async def show_history(update: Update, context: CallbackContext):
    """Показать историю чата"""
    chat_id = str(update.effective_chat.id)

    history_manager = context.bot_data.get('history_manager')
    if not history_manager:
        await update.message.reply_text("❌ Система истории сообщений не инициализирована")
        return

    messages = history_manager.get_chat_history(chat_id)

    if not messages:
        await update.message.reply_text("📝 История сообщений пуста")
        return

    history_text = "📝 История переписки:\n\n"
    for msg in messages:
        timestamp = datetime.fromisoformat(msg['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
        sender = "🤖 Бот" if msg['is_bot'] else f"👤 {msg['username']}"
        history_text += f"{timestamp} {sender}:\n{msg['text']}\n\n"

    await update.message.reply_text(history_text)


async def clear_history(update: Update, context: CallbackContext):
    """Очистка истории чата"""
    chat_id = str(update.effective_chat.id)

    history_manager = context.bot_data.get('history_manager')
    if history_manager:
        history_manager.clear_chat_history(chat_id)
        await update.message.reply_text("✅ История сообщений очищена")
    else:
        await update.message.reply_text("❌ Система истории сообщений не инициализирована")


async def handle_image_message(update: Update, context: CallbackContext):
    """Обработка изображений"""
    if not update.effective_message or not update.effective_message.photo:
        return

    message = update.effective_message
    chat_type = update.effective_chat.type

    # Получаем информацию об отправителе
    user = message.from_user
    username = user.username if user else None

    caption = message.caption or ''

    try:
        # Сохраняем сообщение
        history_manager = context.bot_data.get('history_manager')
        if not history_manager:
            context.bot_data['history_manager'] = ChatHistoryManager()
            history_manager = context.bot_data['history_manager']

        # Формируем данные сообщения
        message_data = {
            'message_id': message.message_id,
            'from_user': user.to_dict(),
            'text': f"[Изображение]{' с подписью: ' + caption if caption else ''}",
            'entities': message.caption_entities if message.caption_entities else []
        }

        history_manager.add_message(message_data)

        # Если вам не нужна дальнейшая обработка изображений, можете оставить эту функцию так
        return

    except Exception as e:
        logging.error(f"Ошибка при обработке изображения: {e}")
        return


async def add_trigger(update: Update, context: CallbackContext):
    """Добавление нового триггерного слова"""
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /add_trigger <триггерное_слово>")
        return

    new_trigger = context.args[0].lower()

    if chat_id not in chat_triggers:
        chat_triggers[chat_id] = set(DEFAULT_TRIGGERS)

    chat_triggers[chat_id].add(new_trigger)

    await update.message.reply_text(f"✅ Триггерное слово '{new_trigger}' добавлено\n"
                                    f"Текущие триггеры: {', '.join(sorted(chat_triggers[chat_id]))}")


async def remove_trigger(update: Update, context: CallbackContext):
    """Удаление триггерного слова"""
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /remove_trigger <триггерное_слово>")
        return

    trigger = context.args[0].lower()

    if chat_id not in chat_triggers:
        chat_triggers[chat_id] = set(DEFAULT_TRIGGERS)

    if trigger in chat_triggers[chat_id]:
        chat_triggers[chat_id].remove(trigger)
        await update.message.reply_text(f"✅ Триггерное слово '{trigger}' удалено\n"
                                        f"Текущие триггеры: {', '.join(sorted(chat_triggers[chat_id]))}")
    else:
        await update.message.reply_text(f"❌ Триггерное слово '{trigger}' не найдено")


async def list_triggers(update: Update, context: CallbackContext):
    """Показать список текущих триггерных слов"""
    chat_id = str(update.effective_chat.id)

    triggers = chat_triggers.get(chat_id, DEFAULT_TRIGGERS)
    await update.message.reply_text(f"📝 Текущие триггерные слова:\n{', '.join(sorted(triggers))}")


async def set_system_instructions(update: Update, context: CallbackContext):
    """Установка системных инструкций для бота"""
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /set_instructions <инструкции>\n"
            "Текущие системные инструкции:\n"
            f"{context.bot_data.get('gemini_tester').system_instructions}"
        )
        return

    new_instructions = " ".join(context.args)
    try:
        gemini_instance = context.bot_data.get('gemini_tester')
        if gemini_instance:
            gemini_instance.system_instructions = new_instructions
            gemini_instance.model = gemini_instance._initialize_model()
            await update.message.reply_text("✅ Системные инструкции обновлены")
        else:
            await update.message.reply_text("❌ Ошибка: экземпляр GeminiTester не найден")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при обновлении инструкций: {str(e)}")


async def handle_new_chat_members(update: Update, context: CallbackContext):
    """Обработка добавления бота в новый чат"""
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:  # Если добавили нашего бота
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="👋 Привет! Я готов помогать в вашем чате.\n"
                     f"Чтобы обратиться ко мне, используйте одно из слов: {', '.join(sorted(DEFAULT_TRIGGERS))}\n"
                     "Доступные команды:\n"
                     "/add_trigger - добавить триггерное слово\n"
                     "/remove_trigger - удалить триггерное слово\n"
                     "/list_triggers - показать список триггеров\n"
                     "/style - изменить стиль общения\n"
                     "/clear_history - очистить историю ваших сообщений\n"
                     "/show_history - показать ваши последние сообщения\n"
                     "/set_instructions - установить системные инструкции для бота\n"
                     "/summarize_today - показать сводку сообщений за сегодня\n"
                     "/summarize_hours N - показать сводку за последние N часов\n"
                     "/summarize_alt - альтернативная сводка переписки на форуме"
            )


async def set_style(update: Update, context: CallbackContext):
    """Установка стиля для генерации ответов"""
    if context.args:
        new_style = " ".join(context.args)
        context.chat_data['style_prompt'] = new_style
        await update.message.reply_text(f"✅ Стиль успешно обновлен:\n{new_style}")
    else:
        await update.message.reply_text("ℹ️ Укажите стиль после команды /style.")


async def error_handler(update: object, context: CallbackContext) -> None:
    """Обработчик ошибок для бота"""
    logging.error(f"Exception while handling an update: {context.error}")


DEFAULT_TRIGGERS = {}
chat_triggers = {}


def setup_logging():
    """Настройка логирования с поддержкой UTF-8"""
    # Создаём папку для логов если её нет
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Настраиваем основной логгер
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # Файловый обработчик с явным указанием кодировки
            logging.FileHandler('logs/bot.log', encoding='utf-8'),
            # Обработчик для консоли с игнорированием ошибок кодировки
            logging.StreamHandler(sys.stdout)
        ]
    )


async def main():
    """Главная функция"""
    # Настраиваем логирование
    setup_logging()
    logger = logging.getLogger('main')

    # Инициализируем компоненты
    global gemini_tester
    gemini_tester = GeminiTester(GEMINI_API_KEY)
    logger.info("GeminiTester initialized")

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .arbitrary_callback_data(True)
        .get_updates_read_timeout(42)
        .build()
    )

    # Проверяем доступ к экспорту
    if os.path.exists("chat_export.json"):
        export_size = os.path.getsize("chat_export.json") / (1024 * 1024)
        logger.info(f"Found export file, size: {export_size:.2f} MB")
        try:
            with open("chat_export.json", 'rb') as f:
                parser = ijson.items(f, 'messages.item')
                last_msg = None
                msg_count = 0
                for msg in parser:
                    msg_count += 1
                    if msg_count % 10000 == 0:
                        logger.info(f"Scanned {msg_count} messages...")
                    last_msg = msg
                if last_msg:
                    last_time = datetime.fromtimestamp(int(last_msg['date_unixtime']))
                    logger.info(f"Export contains {msg_count} messages, last message from: {last_time}")
        except Exception as e:
            logger.error(f"Error checking export: {e}")
    else:
        logger.warning("Export file not found")

    # Инициализируем менеджер истории
    history_manager = ChatHistoryManager()
    application.bot_data['history_manager'] = history_manager
    application.bot_data['gemini_tester'] = gemini_tester

    # Добавляем обработчики команд
    for command, handler, desc in [
        ('summarize_today', summarize_today, 'суммаризация за сегодня'),
        ('summarize_hours', summarize_hours, 'суммаризация за период'),
        ('summarize_date', summarize_date, 'суммаризация за дату'),  # Новый обработчик
        ('show_history', show_history, 'показать историю'),
        ('clear_history', clear_history, 'очистить историю'),
        ('style', set_style, 'изменить стиль'),
        ('set_instructions', set_system_instructions, 'изменить инструкции')
    ]:
        application.add_handler(CommandHandler(command, handler))
        logger.info(f"Added handler: {command}")
        logger.info("Added handler: summarize_date")

        logger.info(f"Added handler: {command}")

    # Обработчик сообщений с логированием
    async def logged_message_handler(update: Update, context: CallbackContext):
        if not update.effective_message or not update.effective_message.text:
            return

        message = update.effective_message
        logger.info(f"Message from {message.from_user.username}: {message.text[:50]}...")

        try:
            await handle_message(update, context)
            logger.info("Message processed successfully")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    # Исправляем фильтр в MessageHandler
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            logged_message_handler
        )
    )

    application.add_handler(MessageHandler(filters.PHOTO, handle_image_message))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    application.add_error_handler(error_handler)

    logger.info("Bot startup complete")
    await application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    nest_asyncio.apply()
    asyncio.run(main())

