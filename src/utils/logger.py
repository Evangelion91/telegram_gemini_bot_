import logging
import sys
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
import colorlog
from typing import Optional


class BotLogger:
    """Настройка логирования для бота"""

    def __init__(
            self,
            name: str = "bot",
            log_dir: str = "logs",
            log_level: int = logging.INFO,
            max_bytes: int = 10 * 1024 * 1024,  # 10 MB
            backup_count: int = 5
    ):
        self.name = name
        self.log_dir = log_dir
        self.log_level = log_level
        self.max_bytes = max_bytes
        self.backup_count = backup_count

        self._ensure_log_dir()
        self.logger = self._setup_logger()

    def _ensure_log_dir(self) -> None:
        """Создание директории для логов"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def _setup_logger(self) -> logging.Logger:
        """Настройка логгера"""
        logger = logging.getLogger(self.name)
        logger.setLevel(self.log_level)

        # Очищаем существующие обработчики
        logger.handlers.clear()

        # Форматтер для файла
        file_formatter = logging.Formatter(
            "[%(asctime)s] %(name)s %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Форматтер для консоли с цветами
        console_formatter = colorlog.ColoredFormatter(
            "%(log_color)s[%(asctime)s] %(name)s %(levelname)s: %(message)s%(reset)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red'
            }
        )

        # Файловый обработчик с ротацией
        log_file = os.path.join(
            self.log_dir,
            f"{self.name}_{datetime.now().strftime('%Y%m%d')}.log"
        )
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Консольный обработчик
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        return logger

    def get_child(self, name: str) -> logging.Logger:
        """Получение дочернего логгера"""
        return self.logger.getChild(name)


class LoggerFilter(logging.Filter):
    """Фильтр для логов"""

    def __init__(self, excluded_patterns: Optional[list] = None):
        super().__init__()
        self.excluded_patterns = excluded_patterns or [
            "httpx",
            "httpcore",
            "asyncio",
            "telegram.ext"
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        return not any(
            pattern in record.name
            for pattern in self.excluded_patterns
        )


def setup_logging(
        log_level: int = logging.INFO,
        log_dir: str = "logs",
        excluded_patterns: Optional[list] = None
) -> BotLogger:
    """
    Настройка логирования для всего приложения

    Args:
        log_level: Уровень логирования
        log_dir: Директория для логов
        excluded_patterns: Паттерны для фильтрации

    Returns:
        BotLogger: Настроенный логгер
    """
    # Отключаем стандартные логи
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)

    # Создаём и настраиваем основной логгер
    logger = BotLogger(
        name="telegram_bot",
        log_dir=log_dir,
        log_level=log_level
    )

    # Добавляем фильтр
    log_filter = LoggerFilter(excluded_patterns)
    logger.logger.addFilter(log_filter)

    return logger