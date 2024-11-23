import pytest
import asyncio
import logging
import warnings
from typing import Generator, AsyncGenerator
from _pytest.logging import LogCaptureFixture


def pytest_configure(config):
    """Конфигурация pytest"""
    # Отключаем все предупреждения о незавершенных корутинах
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    warnings.filterwarnings("ignore", category=pytest.PytestUnraisableExceptionWarning)

    # Устанавливаем параметры asyncio
    asyncio.get_event_loop_policy().new_event_loop()


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Отключаем отладку asyncio для уменьшения предупреждений
    loop.set_debug(False)

    yield loop

    # Закрываем все незавершенные задачи
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()

    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()


@pytest.fixture(scope="function", autouse=True)
async def cleanup_pending_tasks():
    """Clean up any pending tasks after each test"""
    yield
    # Получаем текущий цикл событий
    loop = asyncio.get_event_loop()

    # Отменяем все незавершенные задачи
    tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
    for task in tasks:
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


@pytest.fixture(scope="session", autouse=True)
def disable_warnings():
    """Disable specific warnings for all tests."""
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=pytest.PytestUnraisableExceptionWarning)


@pytest.fixture(autouse=True)
def setup_logging(caplog: LogCaptureFixture):
    """Set up logging for tests."""
    caplog.set_level(logging.INFO)

    # Отключаем логи от некоторых модулей
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("pytest_asyncio").setLevel(logging.WARNING)
