from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from flask import current_app

from PIL import Image

from app.utils.image_utils import ALLOWED_IMAGE_EXTS, make_preview_image


def _list_shirt_images(shirts_dir: Path) -> List[Path]:
    if not shirts_dir.exists():
        return []
    files: List[Path] = []
    for p in shirts_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in ALLOWED_IMAGE_EXTS:
            continue
        files.append(p)
    return files


def _preview_is_too_large(preview_path: Path, max_dim: int) -> bool:
    if not preview_path.exists():
        return True
    try:
        with Image.open(preview_path) as img:
            return max(img.width, img.height) > max_dim
    except Exception:
        # Если превью битое/не читается — пересоздадим.
        return True


def list_shirts(query: str | None = None, limit: int = 6) -> tuple[List[dict], int]:
    app = current_app
    shirts_dir = Path(app.config["SHIRTS_DIR"])
    preview_dir = Path(app.config["SHIRTS_PREVIEW_DIR"])

    q = (query or "").strip().lower()
    items = _list_shirt_images(shirts_dir)

    if q:
        items = [p for p in items if q in p.name.lower()]

    # стабильная сортировка
    items.sort(key=lambda p: p.name.lower())
    total = len(items)
    items = items[: max(1, int(limit))]

    result: List[dict] = []
    for p in items:
        preview_name = f"{p.stem}.jpg"
        preview_path = preview_dir / preview_name

        # Создаём превью лениво и пересоздаём, если оно уже слишком большое.
        # Это важно, потому что файлы в preview могут уже существовать с "старым" размером.
        target_max_size: Tuple[int, int] = (180, 180)
        max_dim = 220
        force = _preview_is_too_large(preview_path, max_dim=max_dim)
        make_preview_image(p, preview_path, max_size=target_max_size, force=force)

        result.append(
            {
                "filename": p.name,
                "preview_url": f"/media/shirts/preview/{preview_name}",
                "original_url": f"/media/shirts/original/{p.name}",
            }
        )
    return result, total

