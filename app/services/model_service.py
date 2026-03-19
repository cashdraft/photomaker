"""Сервис списка предзагруженных моделей для генерации."""

from __future__ import annotations

from pathlib import Path

from flask import current_app


def list_models() -> list[dict]:
    """Возвращает список моделей из MODELS_DIR (файлы jpg, png, webp)."""
    models_dir = Path(current_app.config.get("MODELS_DIR", "data/models"))
    if not models_dir.exists():
        return []
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    items = []
    for p in sorted(models_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in allowed:
            items.append({
                "id": p.name,
                "filename": p.name,
                "url": f"/media/models/{p.name}",
            })
    return items


def get_model_path(filename: str) -> Path | None:
    """Возвращает путь к файлу модели или None если не найден."""
    models_dir = Path(current_app.config.get("MODELS_DIR", "data/models"))
    path = models_dir / filename
    if path.is_file():
        return path
    return None
