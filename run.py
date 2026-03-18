from app.main import create_app


app = create_app()


if __name__ == "__main__":
    # Упрощённый запуск для разработки/проверки в браузере.
    # По умолчанию слушаем все интерфейсы, чтобы можно было открыть из другого хоста.
    import os

    host = os.getenv("PHOTOMAKER_HOST", "0.0.0.0")
    port = int(os.getenv("PHOTOMAKER_PORT", "8000"))
    debug = os.getenv("PHOTOMAKER_DEBUG", "0").lower() in {"1", "true", "yes", "on"}

    app.run(host=host, port=port, debug=debug)
