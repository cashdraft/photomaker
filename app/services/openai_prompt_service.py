"""Генерация промпта по референс-картинке через OpenAI Vision."""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

from flask import current_app

logger = logging.getLogger(__name__)


def generate_prompt_for_image(image_path: Path, master_prompt: str | None = None) -> str:
    """
    Отправляет изображение в OpenAI Vision с мастерпромтом и возвращает сгенерированный промпт.

    :param image_path: путь к файлу изображения
    :param master_prompt: инструкция для модели (если None — берётся из config)
    :return: текст промпта
    :raises: ValueError при отсутствии ключа/конфига, RuntimeError при ошибке API
    """
    app = current_app
    api_key = app.config.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY не задан")

    model = app.config.get("OPENAI_MODEL", "gpt-4o")
    prompt = master_prompt or app.config.get("OPENAI_MASTER_PROMPT", "")
    if not prompt:
        raise ValueError("OPENAI_MASTER_PROMPT не задан")

    if not image_path.exists():
        raise FileNotFoundError(f"Файл не найден: {image_path}")

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
    except ImportError as e:
        raise RuntimeError("Пакет openai не установлен") from e

    ext = image_path.suffix.lower()
    mime = "image/jpeg"
    if ext in {".png"}:
        mime = "image/png"
    elif ext in {".webp"}:
        mime = "image/webp"

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    data_url = f"data:{mime};base64,{b64}"
    img_size_kb = len(b64) * 3 // 4 // 1024
    logger.info("Отправка в OpenAI: model=%s, image ~%d KB", model, img_size_kb)

    t0 = time.monotonic()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            }
        ],
        max_completion_tokens=500,
    )
    elapsed = time.monotonic() - t0

    usage = getattr(response, "usage", None)
    usage_info = ""
    if usage:
        usage_info = f", usage: prompt_tokens={getattr(usage, 'prompt_tokens', '?')}, completion_tokens={getattr(usage, 'completion_tokens', '?')}"
    logger.info("OpenAI ответ: elapsed=%.1f сек%s, finish_reason=%s", elapsed, usage_info, getattr(response.choices[0], "finish_reason", "?"))

    text = response.choices[0].message.content
    return (text or "").strip()
