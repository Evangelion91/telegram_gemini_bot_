# Документация методов и классов

## 1. Core Components

### GeminiClient (src/core/gemini_client.py)
Клиент для работы с Gemini API.

#### Методы:
1. `__init__(api_key, model_name, system_instructions, logger)`
   - Инициализирует клиент Gemini
   - Устанавливает API ключ и базовые параметры
   - Настраивает логгер
   - Создает модель с начальными инструкциями

2. `_initialize_model()`
   - Создает экземпляр модели Gemini
   - Устанавливает базовую конфигурацию (токены, температура и т.д.)
   - Возвращает инициализированную модель

3. `_get_safety_settings()`
   - Возвращает настройки безопасности для модели
   - Отключает фильтры для более свободной генерации

4. `generate_text(prompt, generation_config, max_retries)`
   - Асинхронно генерирует текстовый ответ
   - Добавляет системные инструкции к промпту
   - Обрабатывает ошибки и повторяет попытки при неудаче
   - Возвращает структурированный ответ GeminiResponse

5. `generate_with_image(prompt, image_path, generation_config, max_retries)`
   - Асинхронно генерирует ответ на основе текста и изображения
   - Обрабатывает загрузку и проверку изображения
   - Стримит ответ для больших генераций
   - Обрабатывает ошибки и таймауты

6. `update_system_instructions(new_instructions)`
   - Обновляет системные инструкции
   - Реинициализирует модель с новыми параметрами

### MessageRouter (src/core/message_router.py)
Маршрутизатор входящих сообщений.

#### Методы:
1. `__init__(default_triggers, logger)`
   - Инициализирует роутер с базовыми триггерами
   - Настраивает логгер
   - Создает хранилище для триггеров чатов

2. `process_update(update, context)`
   - Обрабатывает входящее обновление Telegram
   - Определяет тип сообщения и необходимость ответа
   - Создает контекст сообщения MessageContext
   - Проверяет триггеры и команды

3. `add_command_handler(command, handler)`
   - Регистрирует обработчик для команды
   - Связывает команду с функцией-обработчиком

4. `add_message_handler(handler)`
   - Добавляет обработчик для обычных сообщений

5. `add_chat_trigger(chat_id, trigger)`
   - Добавляет новый триггер для конкретного чата
   - Обновляет список триггеров чата

6. `remove_chat_trigger(chat_id, trigger)`
   - Удаляет триггер из чата
   - Возвращает успех операции

7. `get_chat_triggers(chat_id)`
   - Возвращает все активные триггеры для чата
   - Объединяет дефолтные и кастомные триггеры

### BotManager (src/core/bot_manager.py)
Основной менеджер бота.

#### Методы:
1. `__init__(telegram_token, gemini_api_key, default_triggers, logger)`
   - Инициализирует основные компоненты бота
   - Создает экземпляры GeminiClient и MessageRouter
   - Настраивает приложение Telegram

2. `setup()`
   - Регистрирует все обработчики
   - Настраивает фильтры сообщений
   - Инициализирует обработку ошибок

3. `handle_message(update, context)`
   - Основной обработчик текстовых сообщений
   - Очищает сообщения от триггеров
   - Генерирует и отправляет ответы

4. `handle_media(update, context)`
   - Обрабатывает медиа-сообщения
   - Загружает и обрабатывает изображения
   - Генерирует описания и ответы

5. `_send_response(update, context, text, reply_to_message_id)`
   - Отправляет ответ с правильным форматированием
   - Обрабатывает ошибки форматирования
   - Поддерживает разные режимы разметки

6. `_clean_message(message, triggers)`
   - Очищает сообщение от триггерных слов
   - Сохраняет оригинальный регистр

7. `_build_prompt(style, message, username, is_bot, is_image)`
   - Создает промпт для Gemini
   - Учитывает стиль и контекст
   - Добавляет специфические инструкции

8. `run()`
   - Запускает бота
   - Инициализирует поллинг обновлений

## 2. Features

### HistoryManager (src/features/history/manager.py)
Управление историей сообщений.

#### Методы:
1. `__init__(storage_dir, export_file, max_messages, logger)`
   - Инициализирует менеджер истории
   - Создает директории хранения
   - Настраивает параметры хранения

2. `load_all_histories()`
   - Загружает все истории чатов
   - Инициализирует кэш историй

3. `add_message(chat_id, message_data)`
   - Добавляет новое сообщение в историю
   - Форматирует данные сообщения
   - Контролирует лимиты сообщений

4. `get_messages(chat_id, start_time, end_time, limit)`
   - Получает сообщения за период
   - Объединяет данные из экспорта и текущей истории
   - Сортирует и фильтрует сообщения

5. `clear_chat_history(chat_id)`
   - Очищает историю конкретного чата
   - Сохраняет изменения

# Детальная документация методов

## 1. GeminiClient (src/core/gemini_client.py)

### Класс GeminiResponse

```python
@dataclass
class GeminiResponse:
    success: bool            # Успешность запроса
    text: Optional[str]      # Сгенерированный текст
    error: Optional[str]     # Сообщение об ошибке
    metadata: Optional[Dict] # Дополнительные данные
    response_object: Any     # Исходный ответ от API
```

### Методы GeminiClient

1. `__init__(api_key: str, model_name: str, system_instructions: str, logger: Optional[logging.Logger]) -> None`
   - Возвращает: None
   - Используется: При создании экземпляра BotManager
   - Параметры:
     * api_key: ключ API Gemini
     * model_name: имя модели (default: "gemini-1.5-flash-002")
     * system_instructions: базовые инструкции для модели
     * logger: объект логгера

2. `_initialize_model() -> GenerativeModel`
   - Возвращает: Инициализированную модель Gemini
   - Используется: В __init__ и update_system_instructions
   - Внутренний метод для создания модели с заданными параметрами

3. `_get_safety_settings() -> Dict[HarmCategory, HarmBlockThreshold]`
   - Возвращает: Словарь настроек безопасности
   - Используется: В generate_text и generate_with_image
   - Внутренний метод конфигурации фильтров

4. `async generate_text(prompt: str, generation_config: Optional[GenConfig] = None, max_retries: int = 3) -> GeminiResponse`
   - Возвращает: GeminiResponse с результатом генерации
   - Используется: В MessageHandlers.handle_text_message и SummaryGenerator
   - Параметры:
     * prompt: текст запроса
     * generation_config: настройки генерации
     * max_retries: количество попыток
   - Пример использования:
     
   - ```python
     response = await gemini.generate_text("Привет, как дела?")
     if response.success:
         message_text = response.text
     ```

5. `async generate_with_image(prompt: str, image_path: str, generation_config: Optional[GenConfig] = None, max_retries: int = 3) -> GeminiResponse`
   - Возвращает: GeminiResponse с результатом анализа изображения
   - Используется: В MessageHandlers.handle_image_message
   - Параметры:
     * prompt: текст запроса
     * image_path: путь к изображению
     * generation_config: настройки генерации
     * max_retries: количество попыток
   - Пример использования:
     ```python
     response = await gemini.generate_with_image(
         "Опиши что на картинке",
         "path/to/image.jpg"
     )
     ```

## 2. MessageRouter (src/core/message_router.py)

### Класс MessageContext
```python
@dataclass
class MessageContext:
    update: Update                # Объект обновления Telegram
    context: CallbackContext      # Контекст обработчика
    chat_id: str                 # ID чата
    user_id: str                 # ID пользователя
    username: Optional[str]      # Имя пользователя
    message_text: Optional[str]  # Текст сообщения
    is_bot: bool                # Является ли отправитель ботом
    chat_type: str              # Тип чата (private/group/etc)
    is_reply_to_bot: bool       # Ответ на сообщение бота
    is_command: bool            # Является ли командой
    command_args: List[str]     # Аргументы команды
    triggers_matched: Set[str]   # Сработавшие триггеры
```

### Методы MessageRouter

1. `__init__(default_triggers: Set[str], logger: Optional[logging.Logger]) -> None`
   - Возвращает: None
   - Используется: При создании экземпляра BotManager
   - Параметры:
     * default_triggers: набор стандартных триггеров
     * logger: объект логгера
   - Инициализирует:
     * self.default_triggers: Set[str]
     * self.chat_triggers: Dict[str, Set[str]]
     * self.command_handlers: Dict[str, Callable]
     * self.message_handlers: List[Callable]

2. `async process_update(update: Update, context: CallbackContext) -> Optional[MessageContext]`
   - Возвращает: MessageContext или None если обработка не требуется
   - Используется: В BotManager.handle_message
   - Параметры:
     * update: обновление от Telegram
     * context: контекст обработчика
   - Пример использования:
     ```python
     msg_context = await router.process_update(update, context)
     if msg_context and msg_context.triggers_matched:
         await handle_triggered_message(msg_context)
     ```

3. `add_command_handler(command: str, handler: Callable[[Update, CallbackContext], Awaitable[Any]]) -> None`
   - Возвращает: None
   - Используется: В BotManager.setup для регистрации команд
   - Параметры:
     * command: название команды без "/"
     * handler: асинхронная функция-обработчик
   - Пример использования:
     ```python
     router.add_command_handler("start", start_handler)
     ```

4. `get_chat_triggers(chat_id: str) -> Set[str]`
   - Возвращает: Множество активных триггеров для чата
   - Используется: В MessageHandlers.handle_text_message
   - Параметры:
     * chat_id: идентификатор чата
   - Пример использования:
     ```python
     triggers = router.get_chat_triggers("123456")
     if any(trigger in message.text for trigger in triggers):
         await process_triggered_message()
     ```

## 3. HistoryManager (src/features/history/manager.py)

### Класс MessageData

```python
@dataclass
class MessageData:
    id: int                      # ID сообщения
    type: str                    # Тип сообщения
    date: str                    # Дата в ISO формате
    date_unixtime: str          # Unix timestamp
    from_user: str              # Отправитель
    from_id: str                # ID отправителя
    text: str                   # Текст сообщения
    is_bot: bool                # От бота ли сообщение
    reply_to_message_id: Optional[int] # ID сообщения-ответа
    entities: List[Dict]        # Сущности сообщения
    media_type: Optional[str]   # Тип медиа
    media_file_id: Optional[str] # ID медиафайла
```

### Методы HistoryManager

1. `__init__(storage_dir: str, export_file: str, max_messages: int, logger: Optional[logging.Logger]) -> None`
   - Возвращает: None
   - Используется: При инициализации BotManager
   - Создает структуру:
     ```python
     self.chat_histories: Dict[str, Dict[str, List[MessageData]]]
     ```


2. `add_message(chat_id: str, message_data: Dict[str, Any]) -> None`
   - Возвращает: None
   - Используется: В MessageHandlers при обработке новых сообщений
   - Параметры:
     * chat_id: идентификатор чата
     * message_data: словарь с данными сообщения
   - Сохраняет в структуру:
     ```python
     self.chat_histories[chat_id]['messages'].append(MessageData(**formatted_data))
     ```
   - Пример использования:
     ```python
     history_manager.add_message("123456", {
         'message_id': 1,
         'from_user': {'id': 123, 'username': 'user'},
         'text': 'Hello'
     })
     ```

3. `get_messages(
       chat_id: str,
       start_time: Optional[datetime] = None,
       end_time: Optional[datetime] = None,
       limit: Optional[int] = None
   ) -> List[Dict[str, Any]]`
   - Возвращает: Список сообщений за период
   - Используется: В SummaryGenerator и CommandHandlers
   - Параметры:
     * chat_id: идентификатор чата
     * start_time: начало периода
     * end_time: конец периода
     * limit: ограничение количества сообщений
   - Пример использования:
     ```python
     messages = history_manager.get_messages(
         chat_id="123456",
         start_time=datetime.now() - timedelta(hours=24)
     )
     ```

4. `clear_chat_history(chat_id: str) -> None`
   - Возвращает: None
   - Используется: В CommandHandlers.handle_clear_history
   - Удаляет все сообщения чата из памяти и файла
   - Пример использования:
     ```python
     await handle_clear_command(update: Update, context: CallbackContext):
         history_manager.clear_chat_history(str(update.effective_chat.id))
     ```

5. `get_chat_context(chat_id: str, message_limit: int = 5) -> List[Dict[str, Any]]`
   - Возвращает: Список последних сообщений для контекста
   - Используется: В MessageHandlers для формирования контекста
   - Параметры:
     * chat_id: идентификатор чата
     * message_limit: количество последних сообщений
   - Пример использования:
     ```python
     context_messages = history_manager.get_chat_context("123456")
     prompt = build_prompt_with_context(context_messages, new_message)
     ```

## 4. ChatAnalyzer (src/features/summary/analyzer.py)

### Классы данных
```python
@dataclass
class UserActivity:
    message_count: int = 0           # Количество сообщений
    total_length: int = 0            # Общая длина сообщений
    replies_received: int = 0         # Полученные ответы
    replies_sent: int = 0            # Отправленные ответы
    topics_discussed: Set[str] = None # Обсуждаемые темы
    first_message_time: Optional[datetime] = None
    last_message_time: Optional[datetime] = None

@dataclass
class ChatAnalysis:
    total_messages: int              # Всего сообщений
    active_users: Dict[str, UserActivity]  # Активность пользователей
    total_duration: Optional[float] = None  # Длительность обсуждения
    main_topics: List[Tuple[str, int]] = None  # Основные темы
    most_active_periods: List[Tuple[str, int]] = None  # Активные периоды
    interaction_pairs: List[Tuple[Tuple[str, str], int]] = None  # Взаимодействия
    sentiment_stats: Dict[str, float] = None  # Статистика тональности
```

### Методы ChatAnalyzer

1. `__init__(logger: Optional[logging.Logger] = None) -> None`
   - Возвращает: None
   - Инициализирует анализатор с логгером
   - Используется: При создании SummaryGenerator

2. `analyze_messages(messages: List[Dict], include_sentiment: bool = False) -> ChatAnalysis`
   - Возвращает: ChatAnalysis с результатами анализа
   - Используется: В SummaryGenerator.generate_summary
   - Параметры:
     * messages: список сообщений для анализа
     * include_sentiment: включать ли анализ тональности
   - Пример использования:
     ```python
     analysis = analyzer.analyze_messages(chat_messages)
     most_active_user = max(
         analysis.active_users.items(),
         key=lambda x: x[1].message_count
     )[0]
     ```

3. `get_user_patterns(user_stats: Dict[str, UserActivity]) -> Dict[str, str]`
   - Возвращает: Словарь с описанием паттернов поведения пользователей
   - Используется: В SummaryGenerator для описания активности
   - Пример результата:
     ```python
     {
         'user1': "очень активный участник, пишет длинные сообщения",
         'user2': "редкий участник, фокусируется на конкретных темах"
     }
     ```

4. `format_duration(hours: float) -> str`
   - Возвращает: Отформатированную строку длительности
   - Используется: В get_activity_description
   - Примеры:
     * format_duration(0.5) -> "30 минут"
     * format_duration(2.5) -> "2 часов"
     * format_duration(48) -> "2 дней"

5. `get_activity_description(analysis: ChatAnalysis) -> str`
   - Возвращает: Текстовое описание активности в чате
   - Используется: В SummaryGenerator.generate_summary
   - Формирует структурированное описание:
     * Общая статистика
     * Активные пользователи
     * Основные темы
     * Периоды активности
     * Ключевые взаимодействия

## 5. SummaryGenerator (src/features/summary/generator.py)

### Класс данных
```python
@dataclass
class SummaryOptions:
    include_user_patterns: bool = True   # Включать паттерны пользователей
    include_topics: bool = True          # Включать темы
    include_activity: bool = True        # Включать активность
    include_interactions: bool = True     # Включать взаимодействия
    max_length: Optional[int] = None     # Максимальная длина
    style: Optional[str] = None          # Стиль изложения
```


### Методы SummaryGenerator

1. `__init__(gemini_client: GeminiClient, analyzer: Optional[ChatAnalyzer] = None, logger: Optional[logging.Logger] = None) -> None`
   - Возвращает: None
   - Используется: В CommandHandlers при инициализации
   - Параметры:
     * gemini_client: клиент для генерации текста
     * analyzer: анализатор чата (создается новый, если не передан)
     * logger: объект логгера

2. `async generate_summary(messages: List[Dict], options: Optional[SummaryOptions] = None) -> str`
   - Возвращает: Строку с готовой сводкой
   - Используется: В различных команды суммаризации
   - Параметры:
     * messages: список сообщений для анализа
     * options: настройки генерации
   - Пример использования:
     ```python
     summary = await summary_generator.generate_summary(
         messages,
         SummaryOptions(include_user_patterns=True, style="двач")
     )
     ```

3. `_build_summary_prompt(description: str, analysis: ChatAnalysis, options: SummaryOptions) -> str`
   - Возвращает: Строку промпта для Gemini
   - Используется: Внутри generate_summary
   - Параметры:
     * description: базовое описание активности
     * analysis: результаты анализа
     * options: настройки генерации
   - Внутреннее использование:
     ```python
     prompt = self._build_summary_prompt(description, analysis, options)
     response = await self.gemini.generate_text(prompt)
     ```

4. `async generate_daily_summary(messages: List[Dict], style: Optional[str] = None) -> str`
   - Возвращает: Сводку за день
   - Используется: В CommandHandlers.handle_summarize_today
   - Параметры:
     * messages: сообщения за день
     * style: стиль изложения
   - Пример использования:
     ```python
     daily_summary = await summary_generator.generate_daily_summary(
         today_messages,
         style="двач с мемами"
     )
     ```

5. `async generate_period_summary(messages: List[Dict], hours: float, style: Optional[str] = None) -> str`
   - Возвращает: Сводку за указанный период
   - Используется: В CommandHandlers.handle_summarize_hours
   - Параметры:
     * messages: сообщения за период
     * hours: количество часов
     * style: стиль изложения

6. `async generate_date_summary(messages: List[Dict], target_date: datetime, style: Optional[str] = None) -> str`
   - Возвращает: Сводку за конкретную дату
   - Используется: В CommandHandlers.handle_summarize_date
   - Параметры:
     * messages: сообщения за дату
     * target_date: целевая дата
     * style: стиль изложения

## 6. CommandHandlers (src/handlers/command_handlers.py)

### Методы CommandHandlers

1. `__init__(history_manager: HistoryManager, gemini_client: GeminiClient, logger: Optional[logging.Logger] = None) -> None`
   - Возвращает: None
   - Инициализирует:
     * self.history: менеджер истории
     * self.gemini: клиент Gemini
     * self.summary_generator: генератор сводок
     * self.commands: словарь команд и обработчиков
   - Регистрируемые команды:
     ```python
     self.commands = {
         'start': self.handle_start,
         'help': self.handle_help,
         'add_trigger': self.handle_add_trigger,
         # ... и другие
     }
     ```

2. `async handle_start(update: Update, context: CallbackContext) -> None`
   - Возвращает: None
   - Использование: При команде /start
   - Отправляет: Приветственное сообщение со списком команд
   - Регистрация:
     ```python
     application.add_handler(CommandHandler("start", handlers.handle_start))
     ```

3. `async handle_help(update: Update, context: CallbackContext) -> None`
   - Возвращает: None
   - Использование: При команде /help
   - Отправляет: Подробную справку по использованию бота

4. `async handle_add_trigger(update: Update, context: CallbackContext) -> None`
   - Возвращает: None
   - Использование: При команде /add_trigger
   - Параметры через context.args[0]
   - Пример использования:
     ```python
     /add_trigger новый_триггер
     ```

5. `async handle_set_style(update: Update, context: CallbackContext) -> None`
   - Возвращает: None
   - Использование: При команде /style
   - Сохраняет: Новый стиль в context.chat_data['style_prompt']
   - Пример использования:
     ```python
     /style отвечай как двачер с мемами
     ```

6. `async handle_summarize_today(update: Update, context: CallbackContext) -> None`
   - Возвращает: None
   - Использование: При команде /summarize_today
   - Процесс:
     1. Получает сообщения за сегодня
     2. Генерирует сводку
     3. Отправляет результат

7. `async handle_summarize_hours(update: Update, context: CallbackContext) -> None`
   - Возвращает: None
   - Использование: При команде /summarize_hours
   - Параметры: Количество часов через context.args[0]
   - Пример использования:
     ```python
     /summarize_hours 24
     ```

## 7. MessageHandlers (src/handlers/message_handlers.py)

### Методы MessageHandlers

1. `__init__(history_manager: HistoryManager, gemini_client: GeminiClient, logger: Optional[logging.Logger] = None) -> None`
   - Возвращает: None
   - Инициализирует:
     * self.history: менеджер истории
     * self.gemini: клиент Gemini
     * self.logger: логгер
   - Используется: В BotManager при инициализации

2. `_clean_triggers(text: str, triggers: set) -> str`
   - Возвращает: Очищенный текст сообщения
   - Используется: Внутри handle_text_message
   - Параметры:
     * text: исходный текст
     * triggers: множество триггеров
   - Пример:
     ```python
     text = "Эй, бот, как дела?"
     triggers = {"бот", "эй"}
     cleaned = self._clean_triggers(text, triggers)  # "как дела?"
     ```

3. `_build_prompt(chat_type: str, username: str, message: str, style: Optional[str] = None, is_image: bool = False) -> str`
   - Возвращает: Подготовленный промпт для Gemini
   - Используется: В обработчиках сообщений и изображений
   - Параметры:
     * chat_type: тип чата (private/group)
     * username: имя пользователя
     * message: текст сообщения
     * style: стиль ответа
     * is_image: флаг обработки изображения
   - Структура промпта:
     ```python
     f"""
     {style or default_style}
     Тип чата: {chat_type}
     От пользователя {username}:
     {message}
     """
     ```

4. `async handle_text_message(update: Update, context: CallbackContext) -> None`
   - Возвращает: None
   - Используется: Как основной обработчик текстовых сообщений
   - Процесс обработки:
     1. Сохранение в историю
     2. Проверка триггеров
     3. Генерация ответа
     4. Отправка ответа
   - Регистрация:
     ```python
     application.add_handler(
         MessageHandler(
             filters.TEXT & ~filters.COMMAND,
             message_handlers.handle_text_message
         )
     )
     ```

5. `async handle_image_message(update: Update, context: CallbackContext) -> None`
   - Возвращает: None
   - Используется: Как обработчик сообщений с изображениями
   - Процесс обработки:
     1. Сохранение изображения во временный файл
     2. Обработка через Gemini Vision
     3. Генерация описания
     4. Удаление временного файла
   - Пример работы с файлами:
     ```python
     temp_filename = f"temp_{uuid.uuid4()}.jpg"
     try:
         await photo_file.download_to_drive(temp_filename)
         response = await self.gemini.generate_with_image(...)
     finally:
         os.remove(temp_filename)
     ```

6. `async handle_new_chat_members(update: Update, context: CallbackContext) -> None`
   - Возвращает: None
   - Используется: При добавлении бота в новый чат
   - Отправляет: Приветственное сообщение с инструкциями
   - Регистрация:
     ```python
     application.add_handler(
         MessageHandler(
             filters.StatusUpdate.NEW_CHAT_MEMBERS,
             message_handlers.handle_new_chat_members
         )
     )
     ```

## 8. Logger (src/utils/logger.py)

### Класс BotLogger

1. `__init__(name: str = "bot", log_dir: str = "logs", log_level: int = logging.INFO, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5) -> None`
   - Возвращает: None
   - Параметры:
     * name: имя логгера
     * log_dir: директория для логов
     * log_level: уровень логирования
     * max_bytes: максимальный размер файла
     * backup_count: количество резервных копий
   - Создает:
     * Файловый обработчик с ротацией
     * Консольный обработчик с цветным форматированием

2. `_ensure_log_dir() -> None`
   - Возвращает: None
   - Создает директорию для логов если её нет
   - Используется: В __init__

3. `_setup_logger() -> logging.Logger`
   - Возвращает: Настроенный объект Logger
   - Настройки:
     * Два обработчика (файл + консоль)
     * Цветное форматирование для консоли
     * Ротация файлов по размеру

4. `get_child(name: str) -> logging.Logger`
   - Возвращает: Дочерний логгер
   - Используется: Для создания логгеров компонентов
   - Пример:
     ```python
     logger = bot_logger.get_child("gemini_client")
     logger.info("Initializing Gemini client...")
     ```

### Класс LoggerFilter

1. `__init__(excluded_patterns: Optional[list] = None) -> None`
   - Возвращает: None
   - Параметры:
     * excluded_patterns: список паттернов для фильтрации
   - По умолчанию фильтрует:
     * "httpx"
     * "httpcore"
     * "asyncio"
     * "telegram.ext"

2. `filter(record: logging.LogRecord) -> bool`
   - Возвращает: True если лог нужно сохранить
   - Используется: Автоматически системой логирования
   - Проверяет: Не входит ли имя записи в excluded_patterns

## 9. Config (src/config.py)

### Класс BotConfig
```python
@dataclass
class BotConfig:
    # Обязательные параметры
    TELEGRAM_TOKEN: str
    GEMINI_API_KEY: str
    ADMIN_CHAT_ID: str

    # Параметры бота
    DEFAULT_TRIGGERS: Set[str] = {
        'сосаня', 'александр', '@Chuvashini_bot', 
        'чуваш', 'саня', 'сань'
    }
    
    # Настройки логирования
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    
    # Пути к файлам
    HISTORY_DIR: str = "chat_history"
    LOG_DIR: str = "logs"
    TEMP_DIR: str = "temp"
    
    # Ограничения
    MAX_MESSAGES_PER_CHAT: int = 50
    MESSAGE_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    
    # Настройки Gemini
    GEMINI_MODEL_NAME: str = "gemini-1.5-flash-002"
    MAX_OUTPUT_TOKENS: int = 1000
    TEMPERATURE: float = 1.0
    TOP_P: float = 1.0
    TOP_K: int = 40
```

### Методы BotConfig

1. `@classmethod from_env(cls) -> 'BotConfig'`
   - Возвращает: Экземпляр BotConfig
   - Использует: Переменные окружения
   - Пример использования:
     ```python
     config = BotConfig.from_env()
     ```
   - Требуемые переменные окружения:
     * TELEGRAM_TOKEN
     * GEMINI_API_KEY
     * ADMIN_CHAT_ID

2. `validate(self) -> None`
   - Возвращает: None
   - Проверяет: Наличие обязательных параметров
   - Вызывает: ValueError при отсутствии параметров
   - Пример использования:
     ```python
     config = BotConfig.from_env()
     try:
         config.validate()
     except ValueError as e:
         logger.error(f"Invalid config: {e}")
         sys.exit(1)
     ```

### Класс UserStyles

1. `STYLES: Dict[str, str]`
   - Словарь стилей общения для разных пользователей
   - Структура:
     ```python
     STYLES = {
         'username': 'описание_стиля',
         'slona_kupi': 'отвечай с наигранной вежливостью...',
         # ...
     }
     ```

2. `@classmethod get_style(cls, username: str) -> str`
   - Возвращает: Строку с описанием стиля для пользователя
   - Параметры:
     * username: имя пользователя
   - Пример использования:
     ```python
     style = UserStyles.get_style('slona_kupi')
     prompt = f"{style}\n{base_prompt}"
     ```

## 10. Main Application (src/main.py)

### Основные функции

1. `async main() -> None`
   - Возвращает: None
   - Основная точка входа приложения
   - Последовательность инициализации:
     1. Загрузка конфигурации
     2. Настройка логирования
     3. Инициализация компонентов
     4. Регистрация обработчиков
     5. Запуск бота
   - Структура работы:
     ```python
     async def main():
         config = BotConfig.from_env()
         logger = setup_logging(...)
         
         try:
             # Инициализация компонентов
             history_manager = HistoryManager(...)
             gemini_client = GeminiClient(...)
             bot_manager = BotManager(...)
             
             # Регистрация обработчиков
             command_handlers = CommandHandlers(...)
             message_handlers = MessageHandlers(...)
             
             # Регистрация в приложении
             for command, handler in command_handlers.commands.items():
                 bot_manager.application.add_handler(...)
             
             # Запуск бота
             await bot_manager.application.run_polling(...)
             
         except Exception as e:
             logger.error(f"Critical error: {e}")
             raise
     ```

2. `if __name__ == "__main__":` блок
   - Применяет nest_asyncio для работы в интерактивных средах
   - Запускает основной цикл событий
   - Код:
     ```python
     if __name__ == "__main__":
         nest_asyncio.apply()
         asyncio.run(main())
     ```

### Структура импортов
```python
# Стандартные библиотеки
import asyncio
import nest_asyncio

# Компоненты бота
from config import BotConfig
from core.bot_manager import BotManager
from core.gemini_client import GeminiClient
from features.history.manager import HistoryManager
from features.summary.generator import SummaryGenerator
from handlers.command_handlers import CommandHandlers
from handlers.message_handlers import MessageHandlers
from utils.logger import setup_logging
```

### Обработка ошибок

1. Глобальная обработка:
   ```python
   try:
       # Инициализация и запуск
   except Exception as e:
       logger.error(f"Critical error: {e}")
       if config.ADMIN_CHAT_ID:
           await notify_admin(e)
       raise
   ```

2. Уведомление администратора:
   ```python
   async def notify_admin(error: Exception) -> None:
       try:
           await bot.send_message(
               chat_id=config.ADMIN_CHAT_ID,
               text=f"❌ Критическая ошибка: {str(error)}"
           )
       except Exception as e:
           logger.error(f"Failed to notify admin: {e}")
   ```

### Механизм перезапуска
```python
async def run_with_restart():
    while True:
        try:
            await main()
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            await asyncio.sleep(5)  # Пауза перед перезапуском
```

