from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests


logger = logging.getLogger(__name__)


@dataclass
class YandexDiskFile:
    path: str            # полный путь на Диске (например, "disk:/photomaker/shirts/sub/f.png")
    name: str            # имя файла
    rel_path: str        # путь относительно корневой синхронизируемой папки, например "sub/f.png"
    size: int            # размер в байтах
    mime_type: str       # MIME-тип
    etag: Optional[str]  # хэш/etag, если вернулся


class YandexDiskClient:
    """
    Минимальный клиент под REST API Яндекс.Диска.
    Используем публичный API disk.resources для листинга и скачивания.
    """

    def __init__(self, token: str, base_url: str = "https://cloud-api.yandex.net/v1/disk"):
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"OAuth {self._token}",
                "Accept": "application/json",
            }
        )

    def list_png_files(self, remote_root: str) -> List[YandexDiskFile]:
        """
        Рекурсивно получить список PNG-файлов из указанной директории на Я.Диске.

        remote_root: что-то вроде "/photomaker/shirts"
        Важно: мы считаем, что синхронизируем конкретную папку на твоём Я.Диске
        и всё, что внутри неё (включая поддиректории), мапим в локальную структуру.
        """
        root_prefix = f"disk:{remote_root.rstrip('/')}"

        def walk_dir(path: str, rel_base: str = "") -> List[YandexDiskFile]:
            url = f"{self._base_url}/resources"
            params = {
                "path": path,
                "limit": 1000,
                "fields": "_embedded.items.type,_embedded.items.name,_embedded.items.path,_embedded.items.size,_embedded.items.mime_type,_embedded.items.md5",
            }
            resp = self._session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("_embedded", {}).get("items", [])
            acc: List[YandexDiskFile] = []

            for item in items:
                item_type = item.get("type")
                name = item.get("name") or ""
                item_path = item.get("path")

                if item_type == "dir":
                    # рекурсивно обходим поддиректорию
                    sub_rel_base = f"{rel_base}/{name}" if rel_base else name
                    acc.extend(walk_dir(item_path, sub_rel_base))
                    continue

                mime = item.get("mime_type") or ""
                if not name.lower().endswith(".png"):
                    continue

                rel_path = f"{rel_base}/{name}" if rel_base else name

                acc.append(
                    YandexDiskFile(
                        path=item_path,
                        name=name,
                        rel_path=rel_path,
                        size=item.get("size") or 0,
                        mime_type=mime,
                        etag=item.get("md5"),
                    )
                )

            return acc

        # стартуем обход с "disk:/<remote_root>"
        start_path = root_prefix
        return walk_dir(start_path)

    def download_file(self, remote_path: str, local_path: Path) -> Path:
        """
        Скачать один файл с Я.Диска на локальный диск.
        remote_path: например, "disk:/photomaker/shirts/file.png"
        """
        # 1. Получаем ссылку для скачивания
        url = f"{self._base_url}/resources/download"
        params = {"path": remote_path}
        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        href = resp.json().get("href")
        if not href:
            raise RuntimeError("Yandex Disk did not return download href")

        # 2. Скачиваем файл по href
        with self._session.get(href, stream=True, timeout=60) as r:
            r.raise_for_status()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with local_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        logger.info("Downloaded Yandex.Disk file %s -> %s", remote_path, local_path)
        return local_path

