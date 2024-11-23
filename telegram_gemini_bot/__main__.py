# Создаем __main__.py в src/
from telegram_gemini_bot.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())