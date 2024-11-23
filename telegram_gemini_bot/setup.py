from setuptools import setup, find_packages

setup(
    name="telegram_gemini_bot",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "python-telegram-bot",
        "google-generativeai",
        "colorlog",
        "nest-asyncio",
        "python-dotenv",
        "ijson"
    ]
)