from app.main import create_app


app = create_app()


if __name__ == "__main__":
    # Упрощённый запуск для разработки
    app.run(host="127.0.0.1", port=8000, debug=True)
