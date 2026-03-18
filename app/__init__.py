from flask import Flask

from .config import load_config
from .db import init_db


def create_app() -> Flask:
    app = Flask(__name__)

    # Конфиг из .env / переменных окружения
    load_config(app)

    # Инициализация БД
    init_db(app)

    # Импорт моделей гарантирует регистрацию схемы
    from . import models  # noqa: F401

    # Создание таблиц на старте (проекта пока без миграций)
    with app.app_context():
        from .db import db

        db.create_all()

    # Регистрация blueprints
    from .routes.pages import bp as pages_bp
    from .routes.api import bp as api_bp
    from .routes.media import bp as media_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(media_bp)

    return app
