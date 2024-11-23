import pytest
import asyncio
import logging
import warnings
import sys
from typing import Generator
from _pytest.logging import LogCaptureFixture


def pytest_configure(config):
    """Конфигурация pytest"""
    # Отключаем все предупреждения о незавершенных корутинах
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    warnings.filterwarnings("ignore", category=ResourceWarning)
    warnings.filterwarnings("ignore", category=pytest.PytestUnraisableExceptionWarning)

    # Включаем tracemalloc для лучшей диагностики утечек памяти
    import tracemalloc
    tracemalloc.start()


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for each test case."""
    if sys.platform.startswith("win"):
        # Для Windows используем ProactorEventLoop
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)

    try:
        yield loop
    finally:
        # Закрываем все незавершенные задачи
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()

        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())

        loop.close()
        asyncio.set_event_loop(None)


@pytest.fixture(scope="function", autouse=True)
async def cleanup_pending_tasks(event_loop):
    """Clean up any pending tasks after each test"""
    yield

    # Отменяем все незавершенные задачи
    pending = asyncio.all_tasks(event_loop) - {asyncio.current_task()}
    for task in pending:
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


@pytest.fixture(scope="session", autouse=True)
def disable_warnings():
    """Disable specific warnings for all tests."""
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    warnings.filterwarnings("ignore", category=ResourceWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=pytest.PytestUnraisableExceptionWarning)


@pytest.fixture(autouse=True)
def setup_logging(caplog: LogCaptureFixture):
    """Set up logging for tests."""
    caplog.set_level(logging.INFO)

    # Отключаем логи от некоторых модулей
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("pytest_asyncio").setLevel(logging.WARNING)


def pytest_sessionfinish(session, exitstatus):
    """Cleanup after all tests are done."""
    # Останавливаем tracemalloc
    import tracemalloc
    tracemalloc.stop()
