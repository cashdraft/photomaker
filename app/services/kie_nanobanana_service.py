"""Сервис генерации изображений через Kie.ai Nano Banana Pro API."""

from __future__ import annotations

import base64
import json
import logging
import time
import uuid
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
    """Загружает файл через Base64 в Kie.ai и возвращает downloadUrl.
    При ошибках соединения — повторы (3 попытки) и fallback на api.kie.ai.
    """
    data = file_path.read_bytes()
    from app.utils.image_utils import compute_file_hash
    file_hash = compute_file_hash(file_path)
    logger.info("Kie upload: path=%s upload_path=%s size=%d hash=%s", file_path.name, upload_path, len(data), file_hash[:16])
    b64 = base64.b64encode(data).decode("ascii")
    ext = file_path.suffix.lower()
    mime = "image/png" if ext == ".png" else "image/jpeg" if ext in (".jpg", ".jpeg") else "image/webp"
    base64_data = f"data:{mime};base64,{b64}"

    payload = {
        "base64Data": base64_data,
        "uploadPath": upload_path,
        "fileName": file_name or file_path.name,
    }
    configured_base = current_app.config.get("KIE_FILE_UPLOAD_BASE", KIE_API_BASE)
    upload_bases = [configured_base]
    if configured_base.rstrip("/") != KIE_API_BASE.rstrip("/"):
        upload_bases.append(KIE_API_BASE)
    max_retries = 3
    last_err = None

    for upload_base in upload_bases:
        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    f"{upload_base.rstrip('/')}/api/file-base64-upload",
                    headers=_get_headers(),
                    json=payload,
                    timeout=90,
                )
                result = resp.json()
                if not resp.ok or not result.get("success"):
                    raise RuntimeError(f"Kie base64 upload failed: {result.get('msg', resp.text)}")
                url = result["data"]["downloadUrl"]
                logger.info("Kie upload OK: %s downloadUrl=%s", upload_base, url)
                return url
            except (
                requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.Timeout,
                ConnectionResetError,
            ) as e:
                last_err = e
                logger.warning("Kie upload attempt %d/%d to %s failed: %s", attempt + 1, max_retries, upload_base, e)
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Kie upload failed after retries. Last error: {last_err}")


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


def build_generation_preview(
    reference_prompt: str,
    shirt_filename: str,
    reference_filename: str,
    base_style: str = "base",
    torso_style: str = "chest",
    model_filename: str = "",
) -> dict:
    """
    Возвращает превью задачи генерации: промпт и список прикрепляемых файлов.
    Не требует KIE_API_KEY.
    """
    model_prompt_text = (
        current_app.config.get("KIE_MODEL_PROMPT_TEXT", "Use the provided reference image for the model appearance")
        if model_filename
        else ""
    )
    prompt = _build_prompt(reference_prompt, base_style, torso_style, model_prompt_text)
    files = []
    if model_filename:
        files.append({"role": "model", "name": model_filename})
    files.append({"role": "shirt", "name": shirt_filename})
    if current_app.config.get("KIE_SEND_REFERENCE_IMAGE", False):
        files.append({"role": "reference", "name": reference_filename})
    return {"prompt": prompt, "files": files}


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
    project_id: str | None = None,
) -> str:
    """
    Генерирует изображение через Nano Banana Pro.

    :param reference_prompt: промпт, сгенерированный OpenAI по референсу
    :param shirt_path: путь к файлу принта на диске
    :param reference_path: путь к файлу референса на диске
    :param base_style: base | oversize (из блоков База/Оверсайз)
    :param torso_style: chest | back | both (из блоков Грудь/Спина/Оба)
    :param model_path: путь к фото модели (если выбрана)
    :param model_name: текст для подстановки в {model} (из KIE_MODEL_PROMPT_TEXT при выбранной модели)
    :return: URL сгенерированного изображения
    """
    if not shirt_path.exists():
        raise FileNotFoundError(f"Принт не найден: {shirt_path}")
    if not reference_path.exists():
        raise FileNotFoundError(f"Референс не найден: {reference_path}")

    send_ref = current_app.config.get("KIE_SEND_REFERENCE_IMAGE", False)
    logger.info("KIE_SEND_REFERENCE_IMAGE: ref will%s be sent to Kie", "" if send_ref else " NOT")

    # Уникальный путь для каждой генерации — иначе Kie может кэшировать и возвращать старый принт
    upload_suffix = uuid.uuid4().hex[:12]

    # Порядок: принт (shirt) ПЕРВЫМ — главный субъект, который должен применяться.
    # ref — сцена/поза для размещения.
    image_input = []
    from app.utils.image_utils import compute_file_hash
    shirt_hash = compute_file_hash(shirt_path)[:12]
    logger.info(
        "Kie REQUEST project=%s shirt=%s hash=%s path=%s",
        project_id or "-",
        shirt_path.name,
        shirt_hash,
        shirt_path,
    )
    shirt_url = _upload_file_base64(
        shirt_path,
        f"photomaker/{upload_suffix}/shirt",
        f"shirt_{shirt_hash}_{shirt_path.suffix}",
    )
    image_input.append(shirt_url)
    if send_ref:
        ref_url = _upload_file_base64(
            reference_path, f"photomaker/{upload_suffix}/ref", f"ref_{upload_suffix}{reference_path.suffix}"
        )
        image_input.append(ref_url)
        logger.info("Uploading: shirt=%s, ref=%s", shirt_path.name, reference_path.name)
    else:
        logger.info("Uploading: shirt=%s only", shirt_path.name)
    if model_path and model_path.exists():
        model_url = _upload_file_base64(
            model_path, f"photomaker/{upload_suffix}/model", f"model_{upload_suffix}{model_path.suffix}"
        )
        image_input.append(model_url)
    prompt = _build_prompt(reference_prompt, base_style, torso_style, model_name, master_template)
    # Явно указываем: первый image = принт, применять его именно с этого файла
    prompt = (
        "CRITICAL: The first (or only) image in image_input is the exact print design. "
        "Apply this print to the t-shirt without modification. "
    ) + prompt
    logger.info(
        "Kie createTask: %d images (shirt+%s), prompt_len=%d",
        len(image_input),
        "ref" if send_ref else "no-ref",
        len(prompt),
    )

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
