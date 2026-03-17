from flask import Blueprint, render_template


bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    # Пока просто заглушка, дальше сюда прикрутим выбор футболки и референсов
    return render_template("index.html")

