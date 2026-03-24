"""Сервис генерации видео через Kie.ai grok-imagine/image-to-video."""

from __future__ import annotations

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


def create_video_task(
    image_url: str,
    prompt: str = "",
    mode: str = "normal",
    duration: str = "6",
    resolution: str = "720p",
) -> str:
    """
    Создаёт задачу генерации видео через grok-imagine/image-to-video.

    :param image_url: полный URL изображения (Kie должен иметь к нему доступ)
    :param prompt: текстовое описание желаемого движения (опционально)
    :param mode: fun | normal | spicy (для внешних изображений spicy недоступен)
    :param duration: 6 | 10 | 15 (секунды)
    :param resolution: 480p | 720p
    :return: taskId
    """
    payload = {
        "model": "grok-imagine/image-to-video",
        "input": {
            "image_urls": [image_url],
            "prompt": prompt or "Smooth, subtle motion. Model stands naturally.",
            "mode": mode,
            "duration": duration,
            "resolution": resolution,
        },
    }
    t0 = time.monotonic()
    resp = requests.post(
        f"{KIE_API_BASE}/api/v1/jobs/createTask",
        headers=_get_headers(),
        json=payload,
        timeout=15,
    )
    elapsed = time.monotonic() - t0
    data = resp.json()
    if resp.status_code != 200 or data.get("code") != 200:
        raise RuntimeError(f"Kie video createTask failed: {data.get('msg', resp.text)}")
    logger.info("Kie createTask OK in %.1fs, taskId=%s", elapsed, (data["data"]["taskId"] or "")[:24])
    return data["data"]["taskId"]


def get_video_task_status(task_id: str) -> dict | None:
    """Получает текущий статус задачи Kie без ожидания. Возвращает state, progress, failMsg и т.д."""
    if not task_id or not task_id.strip():
        logger.warning("get_video_task_status: empty task_id")
        return None
    try:
        resp = requests.get(
            f"{KIE_API_BASE}/api/v1/jobs/recordInfo",
            params={"taskId": task_id},
            headers=_get_headers(),
            timeout=15,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code != 200 or data.get("code") != 200:
            logger.warning("Kie recordInfo: status=%s code=%s msg=%s", resp.status_code, data.get("code"), data.get("msg"))
            return None
        rec = data.get("data") or {}
        if isinstance(rec, dict):
            state = rec.get("state", "")
        else:
            state = ""
        out = {
            "state": state,
            "progress": rec.get("progress") if isinstance(rec, dict) else None,
            "failMsg": rec.get("failMsg", "") if isinstance(rec, dict) else "",
            "costTime": rec.get("costTime") if isinstance(rec, dict) else None,
        }
        logger.info("Kie recordInfo task=%s state=%s", task_id[:24], state)
        return out
    except Exception as e:
        logger.warning("Kie recordInfo failed for %s: %s", task_id[:24], e)
        return None


def poll_video_task(task_id: str, max_wait_sec: int = 600, interval_sec: float = 5.0) -> dict:
    """Ожидает завершения видео-задачи и возвращает resultJson."""
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
            raise RuntimeError(rec.get("failMsg", "Video generation failed"))
        logger.info("Kie video task %s: state=%s", task_id[:20], state)
        time.sleep(interval_sec)
    raise TimeoutError(f"Video task {task_id} did not complete in {max_wait_sec}s")
