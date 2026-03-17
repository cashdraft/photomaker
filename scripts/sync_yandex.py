import logging
from pathlib import Path

from app.main import create_app
from app.services.sync_service import sync_shirts_from_yandex


def main() -> None:
    app = create_app()

    # Простой логгер в файл logs/sync.log
    base_dir = Path(app.config["BASE_DIR"])
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "sync.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    with app.app_context():
        sync_shirts_from_yandex()


if __name__ == "__main__":
    main()

