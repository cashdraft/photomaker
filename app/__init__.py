from flask import Flask

from .config import load_config


def _migrate_references_add_generated_prompt(db) -> None:
    """Добавляет колонку generated_prompt в references, если её нет."""
    try:
        result = db.session.execute(
            db.text('PRAGMA table_info("references")'),
        )
        columns = [row[1] for row in result.fetchall()]
        if "generated_prompt" not in columns:
            db.session.execute(
                db.text('ALTER TABLE "references" ADD COLUMN generated_prompt TEXT'),
            )
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


def _migrate_references_add_prompt_error(db) -> None:
    """Добавляет колонку prompt_error в references, если её нет."""
    try:
        result = db.session.execute(
            db.text('PRAGMA table_info("references")'),
        )
        columns = [row[1] for row in result.fetchall()]
        if "prompt_error" not in columns:
            db.session.execute(
                db.text('ALTER TABLE "references" ADD COLUMN prompt_error TEXT'),
            )
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


def _migrate_references_add_prompt_started_at(db) -> None:
    """Добавляет колонку prompt_started_at в references, если её нет."""
    try:
        result = db.session.execute(
            db.text('PRAGMA table_info("references")'),
        )
        columns = [row[1] for row in result.fetchall()]
        if "prompt_started_at" not in columns:
            db.session.execute(
                db.text('ALTER TABLE "references" ADD COLUMN prompt_started_at DATETIME'),
            )
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


def _migrate_references_add_result_paths(db) -> None:
    """Добавляет колонки result_preview_rel_path, result_original_rel_path в references."""
    from app.models import GenerationJob, Reference

    try:
        result = db.session.execute(
            db.text('PRAGMA table_info("references")'),
        )
        columns = [row[1] for row in result.fetchall()]
        if "result_preview_rel_path" not in columns:
            db.session.execute(
                db.text('ALTER TABLE "references" ADD COLUMN result_preview_rel_path VARCHAR(512)'),
            )
            db.session.commit()
        result = db.session.execute(
            db.text('PRAGMA table_info("references")'),
        )
        columns = [row[1] for row in result.fetchall()]
        if "result_original_rel_path" not in columns:
            db.session.execute(
                db.text('ALTER TABLE "references" ADD COLUMN result_original_rel_path VARCHAR(512)'),
            )
            db.session.commit()
        # Backfill: для ref без result — взять из последнего completed job
        jobs = db.session.execute(
            db.text("""
                SELECT reference_id, result_preview_rel_path, result_original_rel_path
                FROM generation_jobs
                WHERE status = 'completed' AND result_preview_rel_path IS NOT NULL
                ORDER BY created_at DESC
            """),
        ).fetchall()
        seen_refs = set()
        for ref_id, preview_path, original_path in jobs:
            if ref_id in seen_refs:
                continue
            seen_refs.add(ref_id)
            db.session.execute(
                db.text(
                    "UPDATE references SET result_preview_rel_path = :p, result_original_rel_path = :o WHERE id = :id AND result_preview_rel_path IS NULL"
                ),
                {"p": preview_path, "o": original_path, "id": ref_id},
            )
        if jobs:
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


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
        _migrate_references_add_generated_prompt(db)
        _migrate_references_add_prompt_error(db)
        _migrate_references_add_prompt_started_at(db)
        _migrate_references_add_result_paths(db)

    # Регистрация blueprints
    from .routes.pages import bp as pages_bp
    from .routes.api import bp as api_bp
    from .routes.media import bp as media_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(media_bp)

    return app
