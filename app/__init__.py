from flask import Flask

from .config import load_config
from .db import init_db


def create_app() -> Flask:
    app = Flask(__name__)

    # Конфиг из .env / переменных окружения
    load_config(app)

    # Инициализация БД
    init_db(app)

    # Регистрация blueprints (пока только страницы)
    from .routes.pages import bp as pages_bp

    app.register_blueprint(pages_bp)

    return app
