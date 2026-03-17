from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Set

from flask import current_app

from app.integrations.yandex_disk_client import YandexDiskClient


logger = logging.getLogger(__name__)


def _load_index(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read sync index %s", path)
        return {}


def _save_index(path: Path, data: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_shirts_from_yandex() -> None:
    """
    Синхронизировать PNG-футболки из Я.Диска в локальную папку data/shirts/original.
    Минимальный v1: тянем новые файлы по имени и md5.
    """
    app = current_app

    token = app.config.get("YANDEX_DISK_TOKEN")
    remote_path = app.config.get("YANDEX_DISK_REMOTE_PATH")
    local_dir = Path(app.config.get("SHIRTS_DIR"))
    sync_state_dir = Path(app.config.get("DATA_DIR")) / "sync_state"
    index_path = sync_state_dir / "shirts_index.json"

    if not token or not remote_path:
        logger.warning("Yandex Disk sync is not configured (missing token or remote path)")
        return

    client = YandexDiskClient(token=token)

    logger.info("Starting Yandex.Disk shirts sync from %s", remote_path)

    # локальный индекс: remote_relative_path -> etag
    local_index: Dict[str, str] = _load_index(index_path)

    remote_files = client.list_png_files(remote_path)
    # ключ — относительный путь внутри синхронизируемой папки,
    # чтобы было однозначное сопоставление remote_subfolder -> local_subfolder
    remote_index: Dict[str, str] = {f.rel_path: (f.etag or "") for f in remote_files}

    existing_paths: Set[str] = set(local_index.keys())
    remote_paths: Set[str] = set(remote_index.keys())

    # новые файлы или изменившиеся
    to_download: Set[str] = set()
    for rel_path in remote_paths:
        remote_etag = remote_index.get(rel_path, "")
        local_etag = local_index.get(rel_path)
        if local_etag != remote_etag:
            to_download.add(rel_path)

    # локальные файлы, которых больше нет на Я.Диске
    to_delete: Set[str] = existing_paths - remote_paths

    logger.info(
        "Yandex.Disk sync: %d remote files, %d local indexed, %d to download/update",
        len(remote_paths),
        len(existing_paths),
        len(to_download),
    )

    for f in remote_files:
        if f.rel_path not in to_download:
            continue

        local_path = local_dir / f.rel_path
        try:
            client.download_file(f.path, local_path)
            local_index[f.rel_path] = f.etag or ""
        except Exception:
            logger.exception("Failed to download Yandex.Disk file %s", f.path)

    # удаляем локальные файлы, которых уже нет на Диске
    for rel_path in to_delete:
        local_file = local_dir / rel_path
        try:
            if local_file.exists():
                local_file.unlink()
                logger.info("Removed local file not present on Yandex.Disk: %s", local_file)
        except Exception:
            logger.exception("Failed to remove local file %s", local_file)
        # убираем из индекса в любом случае
        local_index.pop(rel_path, None)

    _save_index(index_path, local_index)
    logger.info("Yandex.Disk shirts sync finished")

