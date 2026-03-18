from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Tuple

from PIL import Image


ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def compute_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def make_preview_image(
    src_path: Path,
    dst_path: Path,
    *,
    max_size: Tuple[int, int] = (320, 320),
    force: bool = False,
) -> None:
    """
    Создаёт превью, если его ещё нет или если src newer чем dst.
    Сохраняет в JPEG (для стабильности браузера).
    """
    if (
        not force
        and dst_path.exists()
        and dst_path.stat().st_mtime >= src_path.stat().st_mtime
    ):
        return

    ensure_parent_dir(dst_path)

    with Image.open(src_path) as img:
        img = img.convert("RGB")
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        # JPEG для снижения размера; прогресс-рендер в браузере лучше.
        img.save(dst_path, format="JPEG", quality=85, optimize=True)


def make_demo_composite(
    reference_path: Path,
    shirt_path: Path,
    out_original_path: Path,
    out_preview_path: Path,
    *,
    preview_max_size: Tuple[int, int] = (320, 320),
) -> None:
    """
    Демо-генерация (без Kie/NanoBanana):
    просто накладываем уменьшенный принт (shirt image) на низ референса.

    Это не заменяет реальное "наденем футболку на модель",
    но позволяет протестировать end-to-end UI/пайплайн.
    """
    ensure_parent_dir(out_original_path)
    ensure_parent_dir(out_preview_path)

    with Image.open(reference_path) as ref_img, Image.open(shirt_path) as shirt_img:
        ref_img = ref_img.convert("RGB")
        shirt_img = shirt_img.convert("RGB")

        # Нормализуем референс до разумного размера, чтобы генерация не была слишком тяжёлой.
        max_width = 1024
        if ref_img.width > max_width:
            scale = max_width / ref_img.width
            new_h = int(ref_img.height * scale)
            ref_img = ref_img.resize((max_width, new_h), Image.Resampling.LANCZOS)

        # Принт уменьшаем до доли ширины референса
        target_print_width = int(ref_img.width * 0.62)
        if target_print_width < 32:
            target_print_width = 32

        print_scale = target_print_width / shirt_img.width
        target_print_height = int(shirt_img.height * print_scale)
        shirt_resized = shirt_img.resize(
            (target_print_width, target_print_height), Image.Resampling.LANCZOS
        )

        # Позиция: снизу по центру
        x = (ref_img.width - shirt_resized.width) // 2
        y = ref_img.height - shirt_resized.height

        composite = ref_img.copy()
        composite.paste(shirt_resized, (x, y))

        composite.save(out_original_path, format="JPEG", quality=90, optimize=True)

        # превью делаем отдельной функцией (контроль max_size)
        make_preview_image(out_original_path, out_preview_path, max_size=preview_max_size)

