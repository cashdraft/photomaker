import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask


BASE_DIR = Path(__file__).resolve().parent.parent


def load_config(app: Flask) -> None:
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change_me")

    app.config["BASE_DIR"] = str(BASE_DIR)
    app.config["DATA_DIR"] = os.getenv("DATA_DIR", str(BASE_DIR / "data"))
    app.config["DB_PATH"] = os.getenv(
        "DB_PATH", str(BASE_DIR / "database" / "photomaker.db")
    )

    # Папки с файлами
    app.config["SHIRTS_DIR"] = os.getenv(
        "SHIRTS_DIR", str(BASE_DIR / "data" / "shirts" / "original")
    )

    app.config["SHIRTS_PREVIEW_DIR"] = os.getenv(
        "SHIRTS_PREVIEW_DIR", str(BASE_DIR / "data" / "shirts" / "preview")
    )

    app.config["REFERENCES_ORIGINAL_DIR"] = os.getenv(
        "REFERENCES_ORIGINAL_DIR", str(BASE_DIR / "data" / "references" / "original")
    )
    app.config["REFERENCES_PREVIEW_DIR"] = os.getenv(
        "REFERENCES_PREVIEW_DIR", str(BASE_DIR / "data" / "references" / "preview")
    )

    app.config["RESULTS_ORIGINAL_DIR"] = os.getenv(
        "RESULTS_ORIGINAL_DIR", str(BASE_DIR / "data" / "results" / "original")
    )
    app.config["RESULTS_PREVIEW_DIR"] = os.getenv(
        "RESULTS_PREVIEW_DIR", str(BASE_DIR / "data" / "results" / "preview")
    )

    # Yandex Disk
    app.config["YANDEX_DISK_TOKEN"] = os.getenv("YANDEX_DISK_TOKEN", "")
    app.config["YANDEX_DISK_REMOTE_PATH"] = os.getenv(
        "YANDEX_DISK_REMOTE_PATH", "/photomaker/shirts"
    )

