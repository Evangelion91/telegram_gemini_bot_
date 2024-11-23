import pytest
import asyncio
import sys
import logging

# Отключаем лишние логи при тестировании
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)


def run_tests():
    """Запуск всех тестов"""
    args = [
        "-v",  # Подробный вывод
        "--asyncio-mode=auto",  # Автоматический режим для асинхронных тестов
        "tests",  # Директория с тестами
        "-s",  # Показывать print() в тестах
        # "--tb=long",  #  трейсбеки
    ]

    # Добавляем аргументы командной строки
    args.extend(sys.argv[1:])

    # Запускаем тесты
    return pytest.main(args)


if __name__ == "__main__":
    # Устанавливаем цветной вывод
    import colorama

    colorama.init()

    try:
        exit_code = run_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nТестирование прервано пользователем")
        sys.exit(1)
    finally:
        colorama.deinit()
