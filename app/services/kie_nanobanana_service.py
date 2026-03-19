"""Сервис генерации изображений через Kie.ai Nano Banana Pro API."""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path

import requests
from flask import current_app

logger = logging.getLogger(__name__)

KIE_API_BASE = "https://api.kie.ai"


def _get_headers() -> dict:
    api_key = current_app.config.get("KIE_API_KEY")
    if not api_key or api_key.startswith("__PUT_"):
        raise ValueError("KIE_API_KEY не задан. Укажите ключ в .env")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _upload_file_base64(file_path: Path, upload_path: str = "photomaker", file_name: str | None = None) -> str:
    """Загружает файл через Base64 в Kie.ai и возвращает downloadUrl."""
    data = file_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    ext = file_path.suffix.lower()
    mime = "image/png" if ext == ".png" else "image/jpeg" if ext in (".jpg", ".jpeg") else "image/webp"
    base64_data = f"data:{mime};base64,{b64}"

    payload = {
        "base64Data": base64_data,
        "uploadPath": upload_path,
        "fileName": file_name or file_path.name,
    }
    upload_base = current_app.config.get("KIE_FILE_UPLOAD_BASE", KIE_API_BASE)
    resp = requests.post(
        f"{upload_base}/api/file-base64-upload",
        headers=_get_headers(),
        json=payload,
        timeout=60,
    )
    result = resp.json()
    if not resp.ok or not result.get("success"):
        raise RuntimeError(f"Kie base64 upload failed: {result.get('msg', resp.text)}")
    return result["data"]["downloadUrl"]


def _build_prompt(
    reference_prompt: str,
    base_style: str = "base",
    torso_style: str = "chest",
    model: str = "",
    master_template: str | None = None,
) -> str:
    """Собирает итоговый промпт: мастерпромт + промпт референса + модель."""
    template = master_template or current_app.config.get(
        "KIE_MASTER_PROMPT",
        "Marketplace product photo. Fit: {base_style}. Print placement: {torso_style}. "
        "Generate a photorealistic image of a model wearing this print. "
        "Scene: {reference_prompt}. Model: {model}",
    )
    return template.format(
        base_style=base_style,
        torso_style=torso_style,
        reference_prompt=reference_prompt or "professional photo, neutral background",
        model=model or "",
    ).strip()


def _create_task(prompt: str, image_urls: list[str]) -> str:
    """Создаёт задачу в Nano Banana Pro и возвращает taskId."""
    payload = {
        "model": "nano-banana-pro",
        "input": {
            "prompt": prompt,
            "image_input": image_urls,
            "aspect_ratio": "3:4",
            "resolution": "1K",
            "output_format": "png",
        },
    }
    resp = requests.post(
        f"{KIE_API_BASE}/api/v1/jobs/createTask",
        headers=_get_headers(),
        json=payload,
        timeout=30,
    )
    data = resp.json()
    if resp.status_code != 200 or data.get("code") != 200:
        raise RuntimeError(f"Kie createTask failed: {data.get('msg', resp.text)}")
    return data["data"]["taskId"]


def _download_image(url: str, save_path: Path) -> None:
    """Скачивает изображение по URL в файл."""
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(resp.content)


def _poll_task(task_id: str, max_wait_sec: int = 180, interval_sec: float = 3.0) -> dict:
    """Ожидает завершения задачи и возвращает resultJson."""
    url = f"{KIE_API_BASE}/api/v1/jobs/recordInfo"
    start = time.monotonic()
    while time.monotonic() - start < max_wait_sec:
        resp = requests.get(url, params={"taskId": task_id}, headers=_get_headers(), timeout=30)
        data = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"Kie recordInfo failed: {data.get('msg', resp.text)}")
        rec = data.get("data", {})
        state = rec.get("state", "")
        if state == "success":
            result_str = rec.get("resultJson", "{}")
            try:
                return json.loads(result_str)
            except json.JSONDecodeError:
                raise RuntimeError(f"Invalid resultJson: {result_str}")
        if state == "fail":
            raise RuntimeError(rec.get("failMsg", "Generation failed"))
        time.sleep(interval_sec)
    raise TimeoutError(f"Task {task_id} did not complete in {max_wait_sec}s")


def generate_image(
    reference_prompt: str,
    shirt_path: Path,
    reference_path: Path,
    base_style: str = "base",
    torso_style: str = "chest",
    model_path: Path | None = None,
    model_name: str = "",
    master_template: str | None = None,
    out_path: Path | None = None,
) -> str:
    """
    Генерирует изображение через Nano Banana Pro.

    :param reference_prompt: промпт, сгенерированный OpenAI по референсу
    :param shirt_path: путь к файлу принта на диске
    :param reference_path: путь к файлу референса на диске
    :param base_style: base | oversize (из блоков База/Оверсайз)
    :param torso_style: chest | back | both (из блоков Грудь/Спина/Оба)
    :param model_path: путь к фото модели (если выбрана)
    :param model_name: имя модели для промпта {model}
    :return: URL сгенерированного изображения
    """
    if not shirt_path.exists():
        raise FileNotFoundError(f"Принт не найден: {shirt_path}")
    if not reference_path.exists():
        raise FileNotFoundError(f"Референс не найден: {reference_path}")

    image_input = []
    if model_path and model_path.exists():
        logger.info("Uploading images to Kie: model=%s, shirt=%s, ref=%s", model_path.name, shirt_path.name, reference_path.name)
        model_url = _upload_file_base64(model_path, "photomaker/model", "model.jpg")
        image_input.append(model_url)
    else:
        logger.info("Uploading images to Kie: shirt=%s, ref=%s", shirt_path.name, reference_path.name)

    shirt_url = _upload_file_base64(shirt_path, "photomaker/shirt", "shirt.png")
    ref_url = _upload_file_base64(reference_path, "photomaker/ref", "ref.jpg")
    image_input.extend([shirt_url, ref_url])
    prompt = _build_prompt(reference_prompt, base_style, torso_style, model_name, master_template)
    logger.info("Kie Nano Banana prompt: %r", prompt)

    task_id = _create_task(prompt, image_input)
    logger.info("Kie task created: %s", task_id)

    result = _poll_task(task_id)
    urls = result.get("resultUrls", [])
    if not urls:
        raise RuntimeError("No result URLs in Kie response")
    result_url = urls[0]
    if out_path:
        _download_image(result_url, out_path)
    return result_url
