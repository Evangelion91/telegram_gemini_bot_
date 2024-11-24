# C:\Users\gta4r\PycharmProjects\TelegramBot\telegram_gemini_bot\core\gemini_client.py
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import asyncio
import logging
from google.generativeai import configure, GenerativeModel, upload_file
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.generativeai.types import GenerationConfig as GenConfig


@dataclass
class GeminiResponse:
    """Структурированный ответ от Gemini API"""
    success: bool
    text: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    response_object: Optional[Any] = None


class GeminiClient:
    """
    Клиент для работы с Gemini API.
    Поддерживает текстовые и мультимодальные запросы.
    """

    def __init__(
            self,
            api_key: str,
            model_name: str = "gemini-1.5-flash-002",
            system_instructions: str = "",
            logger: Optional[logging.Logger] = None
    ):
        self.logger = logger or logging.getLogger(__name__)
        configure(api_key=api_key)
        self.system_instructions = system_instructions
        self.model_name = model_name
        self.model = self._initialize_model()

    def _initialize_model(self) -> GenerativeModel:
        """Инициализация модели с базовой конфигурацией"""
        base_config = GenConfig(
            candidate_count=1,
            max_output_tokens=1000,
            temperature=1.0,
            top_p=1.0,
            top_k=40
        )

        self.logger.info(f"Initializing model {self.model_name} with config: {base_config}")

        return GenerativeModel(
            model_name=self.model_name,
            generation_config=base_config
        )

    def _get_safety_settings(self) -> Dict[HarmCategory, HarmBlockThreshold]:
        """Получение настроек безопасности"""
        return {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

    async def generate_text(
            self,
            prompt: str,
            generation_config: Optional[GenConfig] = None,
            max_retries: int = 3
    ) -> GeminiResponse:
        """
        Генерация текстового ответа

        Args:
            prompt: Текст запроса
            generation_config: Конфигурация генерации
            max_retries: Количество попыток

        Returns:
            GeminiResponse: Структурированный ответ
        """
        self.logger.debug(f"Generating text for prompt: {prompt[:100]}...")

        for attempt in range(max_retries):
            try:
                full_prompt = f"{self.system_instructions}\n\n{prompt}" if self.system_instructions else prompt

                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.model.generate_content(
                        full_prompt,
                        generation_config=generation_config,
                        safety_settings=self._get_safety_settings()
                    )
                )

                return GeminiResponse(
                    success=True,
                    text=response.text,
                    response_object=response,
                    metadata={
                        'attempt': attempt + 1,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )

            except Exception as e:
                self.logger.error(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                if attempt == max_retries - 1:
                    return GeminiResponse(
                        success=False,
                        error=str(e),
                        metadata={'attempts': attempt + 1}
                    )
                await asyncio.sleep(2 ** attempt)

    async def generate_with_image(
            self,
            prompt: str,
            image_path: str,
            generation_config: Optional[GenConfig] = None,
            max_retries: int = 3
    ) -> GeminiResponse:
        """
        Генерация ответа на основе текста и изображения

        Args:
            prompt: Текст запроса
            image_path: Путь к изображению
            generation_config: Конфигурация генерации
            max_retries: Количество попыток

        Returns:
            GeminiResponse: Структурированный ответ
        """
        try:
            self.logger.debug(f"Processing image from {image_path} with prompt: {prompt[:100]}...")

            uploaded_file = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: upload_file(image_path)
            )

            content = [prompt, uploaded_file]

            base_config = generation_config or GenConfig(
                candidate_count=1,
                max_output_tokens=1000,
                temperature=1.0,
                top_p=1.0,
                top_k=40
            )

            for attempt in range(max_retries):
                try:
                    response = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.model.generate_content(
                                content,
                                stream=True,
                                generation_config=base_config,
                                safety_settings=self._get_safety_settings()
                            )
                        ),
                        timeout=30.0
                    )

                    accumulated_text = []
                    block_reason = None

                    async def process_stream():
                        async for chunk in response:
                            if chunk.text:
                                accumulated_text.append(chunk.text)
                            if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                                nonlocal block_reason
                                block_reason = chunk.prompt_feedback.block_reason

                    await asyncio.wait_for(process_stream(), timeout=30.0)

                    full_text = ''.join(accumulated_text)

                    if full_text:
                        return GeminiResponse(
                            success=True,
                            text=full_text,
                            response_object=response,
                            metadata={
                                'attempt': attempt + 1,
                                'block_reason': block_reason,
                                'timestamp': datetime.utcnow().isoformat()
                            }
                        )

                except asyncio.TimeoutError:
                    self.logger.error(f"Timeout on attempt {attempt + 1}")
                    if attempt == max_retries - 1:
                        return GeminiResponse(
                            success=False,
                            error="Request timeout",
                            metadata={'attempts': attempt + 1}
                        )
                except Exception as e:
                    self.logger.error(f"Error on attempt {attempt + 1}: {e}")
                    if attempt == max_retries - 1:
                        return GeminiResponse(
                            success=False,
                            error=str(e),
                            metadata={'attempts': attempt + 1}
                        )
                await asyncio.sleep(2 ** attempt)

        except Exception as e:
            self.logger.error(f"Fatal error in generate_with_image: {e}")
            return GeminiResponse(
                success=False,
                error=str(e)
            )

    def update_system_instructions(self, new_instructions: str) -> None:
        """Обновление системных инструкций"""
        self.system_instructions = new_instructions
        self.model = self._initialize_model()  # Реинициализация модели с новыми инструкциями