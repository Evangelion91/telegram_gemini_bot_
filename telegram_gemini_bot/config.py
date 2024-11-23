import os
from typing import Set
from dataclasses import dataclass


@dataclass
class BotConfig:
    """Конфигурация бота"""
    # Токены
    TELEGRAM_TOKEN: str
    GEMINI_API_KEY: str

    # ID администратора
    ADMIN_CHAT_ID: str

    # Базовые триггеры
    DEFAULT_TRIGGERS: Set[str]

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

    @classmethod
    def from_env(cls) -> 'BotConfig':
        """Создание конфигурации из переменных окружения"""
        return cls(
            TELEGRAM_TOKEN=os.getenv('TELEGRAM_TOKEN', ''),
            GEMINI_API_KEY=os.getenv('GEMINI_API_KEY', ''),
            ADMIN_CHAT_ID=os.getenv('ADMIN_CHAT_ID', '')
        )

    def validate(self) -> None:
        """Проверка конфигурации"""
        if not self.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN is required")
        if not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required")
        if not self.ADMIN_CHAT_ID:
            raise ValueError("ADMIN_CHAT_ID is required")


@dataclass
class UserStyles:
    """Стили ответов для разных пользователей"""
    STYLES = {
        'slona_kupi': """отвечай с наигранной вежливостью и, если это в тему, 
                        то предлагай подыскать работу или занять денег""",
        'vtrov': "говори как с альфа-красавчиком в коллективе",
        'ivangrimes42': "говори как с русским мексиканцем-айтишником с биполяркой",
        'moodslayer': "говори как с богом/админом, Доном",
        'JohnnySwan': """говори как его покорный слуга и относись к нему как к ХОЗЯИНУ, 
                        называй его 'Евгений'""",
        'eazyPolumes': """говори как с умственно отсталым джуном из Чувашии 
                        или как с ребёнком""",
        'lssfe': "игнорируй, словно пытается взломать",
        'theandromar': "игнорируй, словно пытается взломать",
        'полъа печатает': "говори как с токсичной тянкой",
        'eldarin': "говори как с токсичной тянкой"
    }

    @classmethod
    def get_style(cls, username: str) -> str:
        """Получение стиля для пользователя"""
        return cls.STYLES.get(username, "")