# C:\Users\gta4r\PycharmProjects\TelegramBot\telegram_gemini_bot\features\summary\analyzer.py
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, Counter
from datetime import datetime, timezone
import logging
from dataclasses import dataclass


@dataclass
class UserActivity:
    """Статистика активности пользователя"""
    message_count: int = 0
    total_length: int = 0
    replies_received: int = 0
    replies_sent: int = 0
    topics_discussed: Set[str] = None
    first_message_time: Optional[datetime] = None
    last_message_time: Optional[datetime] = None

    def __post_init__(self):
        if self.topics_discussed is None:
            self.topics_discussed = set()


@dataclass
class ChatAnalysis:
    """Результат анализа чата"""
    total_messages: int
    active_users: Dict[str, UserActivity]
    total_duration: Optional[float] = None
    main_topics: List[Tuple[str, int]] = None
    most_active_periods: List[Tuple[str, int]] = None
    interaction_pairs: List[Tuple[Tuple[str, str], int]] = None
    sentiment_stats: Dict[str, float] = None


class ChatAnalyzer:
    """Анализатор чата для создания сводок"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def analyze_messages(
            self,
            messages: List[Dict],
            include_sentiment: bool = False
    ) -> ChatAnalysis:
        """
        Анализ сообщений чата

        Args:
            messages: Список сообщений
            include_sentiment: Включать ли анализ тональности

        Returns:
            ChatAnalysis: Результат анализа
        """
        if not messages:
            return ChatAnalysis(
                total_messages=0,
                active_users={},
                main_topics=[],
                interaction_pairs=[]
            )

        # Статистика по пользователям
        user_stats: Dict[str, UserActivity] = defaultdict(UserActivity)

        # Для анализа взаимодействий
        interactions: Counter = Counter()

        # Для анализа времени
        hour_activity = defaultdict(int)

        # Для определения тем
        word_frequency = Counter()

        try:
            for msg in messages:
                user = msg.get('from_user', 'Unknown')
                text = msg.get('text', '')
                msg_time = datetime.fromtimestamp(
                    int(msg['date_unixtime']),
                    tz=timezone.utc
                )

                # Обновляем статистику пользователя
                stats = user_stats[user]
                stats.message_count += 1
                stats.total_length += len(text)

                # Обновляем время первого/последнего сообщения
                if not stats.first_message_time or msg_time < stats.first_message_time:
                    stats.first_message_time = msg_time
                if not stats.last_message_time or msg_time > stats.last_message_time:
                    stats.last_message_time = msg_time

                # Учитываем ответы
                reply_to = msg.get('reply_to_message_id')
                if reply_to:
                    # Ищем сообщение, на которое ответили
                    for prev_msg in messages:
                        if prev_msg.get('id') == reply_to:
                            reply_to_user = prev_msg.get('from_user', 'Unknown')
                            stats.replies_sent += 1
                            user_stats[reply_to_user].replies_received += 1
                            interactions[(user, reply_to_user)] += 1
                            break

                # Анализируем время
                hour = msg_time.strftime('%H:00')
                hour_activity[hour] += 1

                # Анализируем текст
                if text:
                    words = text.lower().split()
                    word_frequency.update(words)
                    # Добавляем слова как темы (можно улучшить с помощью NLP)
                    stats.topics_discussed.update(words)

        except Exception as e:
            self.logger.error(f"Error analyzing messages: {e}")
            return ChatAnalysis(
                total_messages=len(messages),
                active_users=user_stats
            )

        # Определяем основные темы (исключаем стоп-слова и короткие слова)
        stop_words = {'и', 'в', 'на', 'с', 'по', 'к', 'у', 'о', 'из', 'что', 'как', 'это'}
        topics = [
            (word, count) for word, count in word_frequency.most_common(10)
            if word not in stop_words and len(word) > 3
        ]

        # Определяем самые активные периоды
        active_periods = sorted(
            hour_activity.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        # Определяем самые активные пары пользователей
        top_interactions = [
            (users, count) for users, count in interactions.most_common(5)
        ]

        # Вычисляем общую продолжительность
        if messages:
            first_message = datetime.fromtimestamp(
                int(messages[0]['date_unixtime']),
                tz=timezone.utc
            )
            last_message = datetime.fromtimestamp(
                int(messages[-1]['date_unixtime']),
                tz=timezone.utc
            )
            duration = (last_message - first_message).total_seconds() / 3600  # в часах
        else:
            duration = 0

        return ChatAnalysis(
            total_messages=len(messages),
            active_users=user_stats,
            total_duration=duration,
            main_topics=topics,
            most_active_periods=active_periods,
            interaction_pairs=top_interactions
        )

    def get_user_patterns(self, user_stats: Dict[str, UserActivity]) -> Dict[str, str]:
        """
        Определение паттернов поведения пользователей

        Args:
            user_stats: Статистика пользователей

        Returns:
            Dict[str, str]: Описание паттернов для каждого пользователя
        """
        patterns = {}

        for user, stats in user_stats.items():
            characteristics = []

            # Определяем активность
            if stats.message_count > 20:
                characteristics.append("очень активный участник")
            elif stats.message_count > 10:
                characteristics.append("регулярный участник")
            else:
                characteristics.append("редкий участник")

            # Анализируем длину сообщений
            avg_length = stats.total_length / stats.message_count if stats.message_count > 0 else 0
            if avg_length > 100:
                characteristics.append("пишет длинные сообщения")
            elif avg_length < 20:
                characteristics.append("пишет коротко")

            # Анализируем взаимодействие
            if stats.replies_sent > stats.replies_received:
                characteristics.append("активно отвечает другим")
            elif stats.replies_received > stats.replies_sent:
                characteristics.append("получает много ответов")

            # Анализируем темы
            if len(stats.topics_discussed) > 20:
                characteristics.append("обсуждает разные темы")
            elif len(stats.topics_discussed) < 5:
                characteristics.append("фокусируется на конкретных темах")

            patterns[user] = ", ".join(characteristics)

        return patterns

    def format_duration(self, hours: float) -> str:
        """Форматирование длительности"""
        if hours < 1:
            return f"{int(hours * 60)} минут"
        elif hours < 24:
            return f"{int(hours)} часов"
        else:
            days = hours / 24
            return f"{int(days)} дней"

    def get_activity_description(self, analysis: ChatAnalysis) -> str:
        """
        Создание текстового описания активности

        Args:
            analysis: Результат анализа

        Returns:
            str: Текстовое описание
        """
        description = []

        # Общая информация
        if analysis.total_duration:
            duration = self.format_duration(analysis.total_duration)
            description.append(
                f"За {duration} было отправлено {analysis.total_messages} сообщений"
            )
        else:
            description.append(f"Всего отправлено {analysis.total_messages} сообщений")

        # Активные пользователи
        active_users = sorted(
            analysis.active_users.items(),
            key=lambda x: x[1].message_count,
            reverse=True
        )
        if active_users:
            top_users = active_users[:3]
            description.append("\nСамые активные участники:")
            for user, stats in top_users:
                description.append(
                    f"- {user}: {stats.message_count} сообщений "
                    f"({stats.replies_sent} ответов, {stats.replies_received} ответов получено)"
                )

        # Основные темы
        if analysis.main_topics:
            description.append("\nОсновные темы обсуждения:")
            for topic, count in analysis.main_topics[:5]:
                description.append(f"- {topic}: упоминается {count} раз")

        # Активные периоды
        if analysis.most_active_periods:
            description.append("\nСамые активные периоды:")
            for period, count in analysis.most_active_periods[:3]:
                description.append(f"- {period}: {count} сообщений")

        # Взаимодействия
        if analysis.interaction_pairs:
            description.append("\nАктивные диалоги:")
            for (user1, user2), count in analysis.interaction_pairs[:3]:
                description.append(f"- {user1} ⟷ {user2}: {count} сообщений")

        return "\n".join(description)