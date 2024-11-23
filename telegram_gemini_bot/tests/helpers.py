import asyncio
from typing import Any, Callable, Coroutine, TypeVar, Optional, AsyncContextManager
from unittest.mock import AsyncMock, Mock
from types import CoroutineType
from contextlib import asynccontextmanager

T = TypeVar('T')


class AsyncTestHelper:
    """Вспомогательный класс для тестирования асинхронного кода"""

    @staticmethod
    async def awaited_mock(
            return_value: Any = None,
            side_effect: Optional[Callable] = None
    ) -> AsyncMock:
        """
        Создает AsyncMock, который можно корректно ожидать

        Args:
            return_value: Значение, которое должен вернуть мок
            side_effect: Функция для side_effect

        Returns:
            AsyncMock: Настроенный асинхронный мок
        """
        mock = AsyncMock()
        if return_value is not None:
            mock.return_value = return_value
        if side_effect is not None:
            mock.side_effect = side_effect

        # Убеждаемся, что мок правильно инициализирован
        try:
            await mock()
        except Exception:
            pass
        mock.reset_mock()
        return mock

    @staticmethod
    @asynccontextmanager
    async def mock_async_context(return_value: Any = None) -> AsyncContextManager[AsyncMock]:
        """
        Создает асинхронный контекстный менеджер-мок

        Args:
            return_value: Значение, которое должен вернуть контекст

        Yields:
            AsyncMock: Настроенный асинхронный мок
        """
        mock = AsyncMock()
        mock.__aenter__ = AsyncMock(return_value=return_value or mock)
        mock.__aexit__ = AsyncMock()
        try:
            yield mock
        finally:
            await AsyncTestHelper.cleanup_mock(mock)

    @staticmethod
    async def cleanup_mock(mock: AsyncMock) -> None:
        """
        Очищает незавершенные корутины в моке

        Args:
            mock: Асинхронный мок для очистки
        """
        if isinstance(mock, (AsyncMock, CoroutineType)):
            try:
                if asyncio.iscoroutinefunction(mock) or isinstance(mock, AsyncMock):
                    await mock()
            except Exception:
                pass
            finally:
                if hasattr(mock, 'reset_mock'):
                    mock.reset_mock()

    @staticmethod
    async def cleanup_mocks(*mocks: AsyncMock) -> None:
        """
        Очищает несколько моков

        Args:
            *mocks: Асинхронные моки для очистки
        """
        for mock in mocks:
            await AsyncTestHelper.cleanup_mock(mock)

    @staticmethod
    async def run_with_timeout(
            coro: Coroutine[Any, Any, T],
            timeout: float = 5.0
    ) -> T:
        """
        Запускает корутину с таймаутом

        Args:
            coro: Корутина для выполнения
            timeout: Таймаут в секундах

        Returns:
            T: Результат выполнения корутины

        Raises:
            TimeoutError: Если выполнение превысило таймаут
        """
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Operation timed out after {timeout} seconds")

    @staticmethod
    async def cleanup_tasks() -> None:
        """Очищает все незавершенные задачи"""
        loop = asyncio.get_running_loop()
        tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]

        for task in tasks:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
