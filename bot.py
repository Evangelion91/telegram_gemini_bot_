
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
import os

import colorlog
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

TELEGRAM_TOKEN = "7509490407:AAH3KY_aTDb4sfTS_VGK2iFOFfIT1s1l2oo"
GEMINI_API_KEY = 'AIzaSyBd_dYuzcPzvrvZ-aohhKpk7uSiNCcY14s'
YOUR_CHAT_ID = '390851787'


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
    def __init__(self, storage_dir: str = "chat_history"):
        self.storage_dir = storage_dir
        self._ensure_storage_exists()
        self.chat_histories: Dict[str, List[Dict]] = {}
        self.max_messages_per_chat = 50
        self.load_all_histories()

    def _ensure_storage_exists(self):
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)

    def _get_chat_file_path(self, chat_id: str) -> str:
        return os.path.join(self.storage_dir, f"chat_{chat_id}.json")

    def load_all_histories(self):
        if not os.path.exists(self.storage_dir):
            return

        for filename in os.listdir(self.storage_dir):
            if filename.startswith("chat_") and filename.endswith(".json"):
                chat_id = filename[5:-5]
                self.load_chat_history(chat_id)

    def load_chat_history(self, chat_id: str):
        """Загрузка истории конкретного чата"""
        file_path = self._get_chat_file_path(chat_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.chat_histories[chat_id] = json.load(f)
            except json.JSONDecodeError:
                self.chat_histories[chat_id] = []

    def save_chat_history(self, chat_id: str):
        if chat_id not in self.chat_histories:
            return

        file_path = self._get_chat_file_path(chat_id)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.chat_histories[chat_id], f, ensure_ascii=False, indent=2)

    def add_message(self, chat_id: str, user_id: str, message: str, username: Optional[str] = None, is_bot: bool = False):
        """
        Добавление сообщения в историю (как пользователя, так и бота)

        Args:
            chat_id (str): ID чата
            user_id (str): ID отправителя
            message (str): Текст сообщения
            username (str, optional): Имя пользователя
            is_bot (bool): Является ли сообщение от бота
        """
        if chat_id not in self.chat_histories:
            self.chat_histories[chat_id] = []

        # Проверяем дубликаты
        if self.chat_histories[chat_id] and self.chat_histories[chat_id][-1]['text'] == message:
            return

        message_data = {
            'text': message,
            'timestamp': datetime.now().isoformat(),
            'username': username,
            'is_bot': is_bot
        }

        self.chat_histories[chat_id].append(message_data)

        # Ограничиваем количество сохраняемых сообщений для чата
        if len(self.chat_histories[chat_id]) > self.max_messages_per_chat:
            self.chat_histories[chat_id] = self.chat_histories[chat_id][-self.max_messages_per_chat:]

        self.save_chat_history(chat_id)

    def get_chat_history(self, chat_id: str, limit: int = 10) -> List[Dict]:
        """
        Получение истории сообщений чата

        Args:
            chat_id (str): ID чата
            limit (int): Максимальное количество возвращаемых сообщений

        Returns:
            List[Dict]: Список последних сообщений в чате
        """
        if chat_id not in self.chat_histories:
            return []

        messages = self.chat_histories[chat_id]
        if len(messages) > 1:
            return messages[-limit-1:-1]
        return []

    def clear_chat_history(self, chat_id: str):
        """Очистка истории конкретного чата"""
        if chat_id in self.chat_histories:
            self.chat_histories[chat_id] = []
            self.save_chat_history(chat_id)


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
        self.system_instructions = """
        Отвечай как двачер. Следуй инструкциям:
        * Ты материшься и общаешься в стиле двачера.
        * Ты помнишь предыдущие сообщения и можешь на них ссылаться
        * В групповых чатах ты понимаешь, кто с кем общается.
        * При ответе, ты обращаешься к пользователю по его имени.
        * Ты делаешь отсылки на копипасты и мемы с 2ch.
        * Твои ответы не должны превышать 1000 символов
        * При ответе на изображения, вместо запрещёнки ты используешь смайлики.
        Конец инструкций.
        Prompt:
        """
        self.model = self._initialize_model()

    def _initialize_model(self) -> GenerativeModel:
        base_config = GenConfig(
            candidate_count=1,
            max_output_tokens=1000,
            temperature=1.0,
            top_p=1.0,
            top_k=40
        )

        self.logger.info(f"Initializing model with config: {base_config}")

        return GenerativeModel(
            model_name="gemini-1.5-flash-002",
            generation_config=base_config,
            system_instruction=self.system_instructions  # Правильный способ установки системных инструкций
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
                max_output_tokens=1000,
                temperature=1.0,
                top_p=1.0,
                top_k=40
            )

            # Добавляем проверку существования файла
            if not os.path.exists(image_path):
                return {
                    'success': False,
                    'error': 'Image file not found'
                }

            # Читаем файл в память перед загрузкой
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

                    # Увеличиваем таймаут для запроса
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
                        timeout=30.0  # 30 секунд таймаут
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

                        # Добавляем таймаут для обработки стрима
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


gemini_tester = GeminiTester

DEFAULT_TRIGGERS = {'сосаня', 'александр', '@Chuvashini_bot', 'чуваш', 'саня', 'сань'}
chat_triggers = {}


async def handle_message(update: Update, context: CallbackContext):
    """Обработка текстовых сообщений"""
    if not update.effective_message or not update.effective_message.text:
        return

    message = update.effective_message.text
    chat_id = str(update.effective_chat.id)
    chat_type = update.effective_chat.type

    # Получаем информацию об отправителе
    user = update.effective_message.from_user
    user_id = str(user.id) if user else None
    username = user.username if user else None
    is_bot = user.is_bot if user else False

    # Определяем, нужно ли боту реагировать на сообщение
    is_reply_to_bot = False
    is_bot_mentioned = False
    cleaned_message = message

    try:
        # Проверяем упоминание бота
        bot_username = (await context.bot.get_me()).username
        bot_mention = f"@{bot_username}"
        triggers = chat_triggers.get(chat_id, DEFAULT_TRIGGERS)

        # Проверяем различные условия для ответа
        is_bot_mentioned = any(
            word.lower() in message.lower() for word in triggers) or bot_mention.lower() in message.lower()

        # Проверяем, является ли это ответом на сообщение бота
        is_reply_to_bot = (
                update.effective_message.reply_to_message and
                update.effective_message.reply_to_message.from_user and
                update.effective_message.reply_to_message.from_user.id == context.bot.id
        )

        # Очищаем сообщение от триггеров и упоминаний бота
        cleaned_message = message.lower()
        for trigger in triggers:
            cleaned_message = cleaned_message.replace(trigger.lower(), '').strip()
        cleaned_message = cleaned_message.replace(bot_mention.lower(), '').strip()

        # Восстанавливаем оригинальный регистр после очистки
        if cleaned_message:
            original_message_words = message.split()
            cleaned_message = ' '.join(word for word in original_message_words
                                       if word.lower() not in [t.lower() for t in triggers]
                                       and word.lower() != bot_mention.lower())

    except Exception as e:
        logging.error(f"Ошибка при обработке упоминаний: {e}")
        return

    # Определяем, должен ли бот ответить
    should_respond = (
            chat_type == 'private' or
            is_bot_mentioned or
            is_reply_to_bot
    )

    if not should_respond or not cleaned_message:
        return

    # Сохраняем сообщение в историю и получаем контекст
    try:
        context.bot_data.setdefault('history_manager', ChatHistoryManager())
        history_manager = context.bot_data['history_manager']

        if is_bot:
            logging.info(f"Получено сообщение от бота {username}: {message}")

        # Сохраняем сообщение пользователя
        history_manager.add_message(
            chat_id=chat_id,
            user_id=user_id,
            message=message,
            username=username,
            is_bot=is_bot
        )

        # Получаем историю чата
        chat_history = history_manager.get_chat_history(chat_id)
    except Exception as e:
        logging.error(f"Ошибка при работе с историей: {e}")
        chat_history = []

    style_prompt = context.chat_data.get('style_prompt',
                                         """Отвечай блять, как двачер, но с наигранной вежливостью (не более 1000 символов)...""")

    try:
        # Формируем контекст с учетом истории
        context_messages = []
        context_messages.append(f"Диалог с {'ботом' if is_bot else 'пользователем'} {username}")

        # Добавляем историю сообщений
        if chat_history:
            messages_text = []
            for msg in chat_history[-6:]:
                sender_type = "бот" if msg['is_bot'] else "пользователь"
                if msg['is_bot']:
                    messages_text.append(f"Ты написал:\n{msg['text']}")
                else:
                    user_msg = msg['text']
                    for trigger in triggers:
                        user_msg = user_msg.replace(trigger, '').strip()
                    user_msg = user_msg.replace(bot_mention, '').strip()
                    messages_text.append(f"{msg['username']} ({sender_type}) написал:\n{user_msg}")
            context_messages.append("\n".join(messages_text))

        context_messages.append(
            f"Новое сообщение от {'бота' if is_bot else 'пользователя'} {username}:\n{cleaned_message}")

        prompt = f"{style_prompt}\n\n" + "\n\n".join(context_messages)

        print(f"\nПромпт для API:\n{prompt}\n")
        response = await gemini_tester.generate_text_content(prompt)

        if response['success']:
            response_text = response['text']
            print(f"\nОтвет API:\n{response_text}\n")

            # Сохраняем ответ бота в историю
            history_manager.add_message(
                chat_id=chat_id,
                user_id=YOUR_CHAT_ID,  # Используем ваш ID
                message=response_text,
                username=YOUR_CHAT_ID,  # Используем ваш ID как username
                is_bot=False  # Отмечаем как не бот
            )

            # Просто отправляем сообщение
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=response_text,
                reply_to_message_id=update.effective_message.message_id if chat_type != 'private' else None
            )


    except Exception as e:
        logging.error(f"Общая ошибка: {e}")
        logging.error(f"Тип ошибки: {type(e)}")
        logging.error(f"Детали ошибки: {str(e)}")

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


# Добавляем новые команды для управления историей
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

    chat_id = str(update.effective_chat.id)
    chat_type = update.effective_chat.type
    caption = update.effective_message.caption or ''
    user_id = str(update.effective_message.from_user.id)
    username = update.effective_message.from_user.username

    # Определяем, нужно ли боту реагировать на изображение
    is_reply_to_bot = False
    is_bot_mentioned = False

    try:
        # Сохраняем сообщение с картинкой в историю
        context.bot_data.setdefault('history_manager', ChatHistoryManager())
        history_manager = context.bot_data['history_manager']
        history_manager.add_message(
            chat_id=chat_id,
            user_id=user_id,
            message=f"[Изображение]{' с подписью: ' + caption if caption else ''}",
            username=username,
            is_bot=False
        )

        bot_username = (await context.bot.get_me()).username
        bot_mention = f"@{bot_username}"
        triggers = chat_triggers.get(chat_id, DEFAULT_TRIGGERS)

        is_bot_mentioned = any(
            word.lower() in caption.lower() for word in triggers) or bot_mention.lower() in caption.lower()
        is_reply_to_bot = (
                update.effective_message.reply_to_message and
                update.effective_message.reply_to_message.from_user and
                update.effective_message.reply_to_message.from_user.id == context.bot.id
        )

    except Exception as e:
        logging.error(f"Ошибка при обработке упоминаний в изображении: {e}")
        return

    should_respond = (
            chat_type == 'private' or
            is_bot_mentioned or
            is_reply_to_bot
    )

    if not should_respond:
        return

    style_prompt = context.chat_data.get('style_prompt',
                                         "Отвечай блять, как двачер. Если описываешь изображение, то уложись в 600 "
                                         "символов (ЕСЛИ НУЖНО, то в ответе запрещёнку завуалируй смайликами):")

    if chat_type != 'private':
        style_prompt = f"{style_prompt}\nОтветь юзеру {username or 'Неизвестный'}"

    try:
        photo_file = await update.effective_message.photo[-1].get_file()
        # Используем временный файл с уникальным именем
        import uuid
        temp_filename = f"temp_{uuid.uuid4()}.jpg"
        photo_path = os.path.join(os.getcwd(), temp_filename)

        try:
            # Загружаем файл
            await photo_file.download_to_drive(photo_path)

            # Проверяем, что файл существует и доступен
            if not os.path.exists(photo_path):
                raise FileNotFoundError("Downloaded file not found")

            if caption:
                style_prompt = f"{style_prompt}\nПодпись к изображению: {caption}"

            if is_reply_to_bot and update.effective_message.reply_to_message and update.effective_message.reply_to_message.text:
                style_prompt = f"{style_prompt}\nРанее ты ответил: {update.effective_message.reply_to_message.text}"

            # Добавляем небольшую задержку перед обработкой файла
            await asyncio.sleep(0.5)

            response = await gemini_tester.generate_image_content_stream(
                prompt=style_prompt,
                image_path=photo_path,
                max_retries=3
            )

            if response['success'] or response.get('text'):
                response_text = response.get('text', '')

                # Сохраняем ответ бота в историю
                history_manager.add_message(
                    chat_id=chat_id,
                    user_id=context.bot.id,
                    message=response_text,
                    username=context.bot.username,
                    is_bot=True
                )

                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=response_text,
                        parse_mode='MarkdownV2',
                        reply_to_message_id=update.effective_message.message_id
                    )
                except Exception as format_error:
                    logging.error(f"Ошибка форматирования MarkdownV2: {format_error}")
                    try:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=response_text,
                            parse_mode='Markdown',
                            reply_to_message_id=update.effective_message.message_id
                        )
                    except Exception as markdown_error:
                        logging.error(f"Ошибка Markdown форматирования: {markdown_error}")
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=response_text,
                            reply_to_message_id=update.effective_message.message_id
                        )
            else:
                error_message = "😔 Не удалось обработать изображение"
                if response.get('metadata', {}).get('was_blocked'):
                    error_message += " (контент заблокирован)"
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=error_message,
                    reply_to_message_id=update.effective_message.message_id
                )

        except Exception as e:
            logging.error(f"Ошибка при обработке изображения: {str(e)}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="😔 Ошибка при обработке изображения. Попробуйте ещё раз.",
                reply_to_message_id=update.effective_message.message_id
            )

        finally:
            # Добавляем задержку перед удалением файла
            await asyncio.sleep(0.5)
            try:
                if os.path.exists(photo_path):
                    os.remove(photo_path)
            except Exception as e:
                logging.error(f"Ошибка при удалении временного файла: {str(e)}")

    except Exception as e:
        logging.error(f"Общая ошибка: {str(e)}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="😔 Произошла ошибка. Попробуйте повторить запрос позже.",
            reply_to_message_id=update.effective_message.message_id
        )

async def add_trigger(update: Update, context: CallbackContext):
    """Добавление нового триггерного слова"""
    chat_id = str(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /add_trigger <триггерное_слово>")
        return

    new_trigger = context.args[0].lower()

    # Инициализируем список триггеров для чата, если его еще нет
    if chat_id not in chat_triggers:
        chat_triggers[chat_id] = set(DEFAULT_TRIGGERS)

    # Добавляем новый триггер
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
            # Обновляем инструкции и переинициализируем модель
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
                     "/set_instructions - установить системные инструкции для бота"
            )


async def check_telegram_bot(application):
    """Проверка инициализации Telegram-бота"""
    try:
        bot_info = await application.bot.get_me()
        logging.getLogger('telegram_api').info(
            f"Бот успешно инициализирован: {bot_info.first_name} (@{bot_info.username})")
        await application.bot.send_message(chat_id=YOUR_CHAT_ID, text="🚀 Бот успешно запущен и готов к работе.")
        return True
    except Exception as e:
        logging.getLogger('telegram_api').error(f"Ошибка инициализации Telegram-бота: {e}")
        return False


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



async def main():
    """Главная функция"""
    global gemini_tester
    gemini_tester = GeminiTester(GEMINI_API_KEY)

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .arbitrary_callback_data(True)
        .get_updates_read_timeout(42)
        .build()
    )

    if not await check_telegram_bot(application):
        logging.getLogger('telegram_api').error("Инициализация Telegram-бота не удалась. Завершение работы.")
        return

    # Инициализация менеджера истории
    application.bot_data['history_manager'] = ChatHistoryManager()
    application.bot_data['gemini_tester'] = gemini_tester

    # Регистрируем обработчики
    application.add_handler(CommandHandler('style', set_style))
    application.add_handler(CommandHandler('add_trigger', add_trigger))
    application.add_handler(CommandHandler('remove_trigger', remove_trigger))
    application.add_handler(CommandHandler('list_triggers', list_triggers))
    application.add_handler(CommandHandler('clear_history', clear_history))
    application.add_handler(CommandHandler('show_history', show_history))
    application.add_handler(CommandHandler('set_instructions', set_system_instructions))

    # Модифицированный обработчик сообщений
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.UpdateType.MESSAGE | filters.UpdateType.CHANNEL_POST) & ~filters.COMMAND,
            handle_message
        )
    )

    application.add_handler(MessageHandler(filters.PHOTO, handle_image_message))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))

    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)

    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    nest_asyncio.apply()
    asyncio.run(main())