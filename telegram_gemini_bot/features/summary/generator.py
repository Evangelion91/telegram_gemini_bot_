# C:\Users\gta4r\PycharmProjects\TelegramBot\telegram_gemini_bot\features\summary\generator.py
from typing import List, Dict, Optional
from datetime import datetime, timezone
import logging
from dataclasses import dataclass

from .analyzer import ChatAnalyzer, ChatAnalysis
from ...core.gemini_client import GeminiClient, GeminiResponse


@dataclass
class SummaryOptions:
    """Настройки генерации сводки"""
    include_user_patterns: bool = True
    include_topics: bool = True
    include_activity: bool = True
    include_interactions: bool = True
    max_length: Optional[int] = None
    style: Optional[str] = None


class SummaryGenerator:
    """Генератор сводок чата"""

    def __init__(
            self,
            gemini_client: GeminiClient,
            analyzer: Optional[ChatAnalyzer] = None,
            logger: Optional[logging.Logger] = None
    ):
        self.gemini = gemini_client
        self.analyzer = analyzer or ChatAnalyzer()
        self.logger = logger or logging.getLogger(__name__)

    async def generate_summary(
            self,
            messages: List[Dict],
            options: Optional[SummaryOptions] = None
    ) -> str:
        """
        Генерация сводки чата

        Args:
            messages: Список сообщений
            options: Настройки генерации

        Returns:
            str: Текст сводки
        """
        if not messages:
            return "📭 Нет сообщений для анализа"

        options = options or SummaryOptions()

        try:
            # Анализируем сообщения
            analysis = self.analyzer.analyze_messages(messages)

            # Получаем базовое описание активности
            description = self.analyzer.get_activity_description(analysis)

            # Генерируем сводку с помощью Gemini
            prompt = self._build_summary_prompt(
                description=description,
                analysis=analysis,
                options=options
            )

            response = await self.gemini.generate_text(prompt)

            if response.success and response.text:
                self.logger.debug(f"Generated response: {response.text}")
                return response.text
            else:
                self.logger.error(f"Failed to generate summary: {response.error}")
                return description

        except Exception as e:
            self.logger.error(f"Error generating summary: {e}")
            return "❌ Произошла ошибка при создании сводки"

    def _build_summary_prompt(
            self,
            description: str,
            analysis: ChatAnalysis,
            options: SummaryOptions
    ) -> str:
        """
        Построение промпта для генерации сводки

        Args:
            description: Базовое описание
            analysis: Результат анализа
            options: Настройки генерации
        """
        prompt_parts = [
            "Проанализируй историю сообщений и создай информативную сводку.",
            "Базовая информация:",
            description
        ]

        if options.include_user_patterns:
            patterns = self.analyzer.get_user_patterns(analysis.active_users)
            prompt_parts.extend([
                "\nПаттерны поведения пользователей:",
                *[f"- {user}: {pattern}" for user, pattern in patterns.items()]
            ])

        prompt_parts.extend([
            "\nТребования к сводке:",
            "1. Сделай акцент на основных темах и динамике обсуждения",
            "2. Опиши роль каждого активного участника",
            "3. Выдели интересные моменты и взаимодействия",
            "4. Подведи итог в стиле 'итого за период...'"
        ])

        if options.style:
            prompt_parts.append(f"\nСтиль изложения: {options.style}")

        if options.max_length:
            prompt_parts.append(f"\nОграничение длины: {options.max_length} символов")

        return "\n".join(prompt_parts)

    async def generate_daily_summary(
            self,
            messages: List[Dict],
            style: Optional[str] = None
    ) -> str:
        """
        Генерация сводки за день

        Args:
            messages: Список сообщений
            style: Стиль изложения

        Returns:
            str: Текст сводки
        """
        options = SummaryOptions(
            include_user_patterns=True,
            include_topics=True,
            include_activity=True,
            include_interactions=True,
            style=style or "Сводка в стиле двачера с юмором и отсылками к мемам"
        )

        return await self.generate_summary(messages, options)

    async def generate_period_summary(
            self,
            messages: List[Dict],
            hours: float,
            style: Optional[str] = None
    ) -> str:
        """
        Генерация сводки за период

        Args:
            messages: Список сообщений
            hours: Количество часов
            style: Стиль изложения

        Returns:
            str: Текст сводки
        """
        options = SummaryOptions(
            include_user_patterns=True,
            include_topics=True,
            include_activity=True,
            include_interactions=True,
            style=style or f"Сводка за последние {hours} часов в стиле двачера"
        )

        return await self.generate_summary(messages, options)

    async def generate_date_summary(
            self,
            messages: List[Dict],
            target_date: datetime,
            style: Optional[str] = None
    ) -> str:
        """
        Генерация сводки за конкретную дату

        Args:
            messages: Список сообщений
            target_date: Дата
            style: Стиль изложения

        Returns:
            str: Текст сводки
        """
        options = SummaryOptions(
            include_user_patterns=True,
            include_topics=True,
            include_activity=True,
            include_interactions=True,
            style=style or f"Сводка за {target_date.strftime('%Y-%m-%d')} в стиле двачера"
        )

        return await self.generate_summary(messages, options)