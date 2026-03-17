from flask import Flask

from . import create_app as _create_app


def create_app() -> Flask:
    """
    Тонкая обёртка, чтобы точка входа была в app.main.
    """
    return _create_app()

