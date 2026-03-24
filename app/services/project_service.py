from __future__ import annotations

import logging
import mimetypes
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, List, Tuple

from flask import current_app

logger = logging.getLogger(__name__)
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.models import GenerationJob, Project, Reference, VideoGeneration
from app.services.openai_prompt_service import generate_prompt_for_image
from app.utils.image_utils import (
    compute_file_hash,
    make_preview_image,
)


def create_project(shirt_filename: str) -> Project:
    app = current_app
    shirts_dir = Path(app.config["SHIRTS_DIR"])
    if not (shirts_dir / shirt_filename).exists():
        raise ValueError("Selected shirt file not found")

    project_id = str(uuid.uuid4())
    project = Project(id=project_id, shirt_filename=shirt_filename)

    # ensure reference/results directories exist
    refs_root = Path(app.config["REFERENCES_ORIGINAL_DIR"]) / project_id
    refs_preview_root = Path(app.config["REFERENCES_PREVIEW_DIR"]) / project_id
    res_root = Path(app.config["RESULTS_ORIGINAL_DIR"]) / project_id
    res_preview_root = Path(app.config["RESULTS_PREVIEW_DIR"]) / project_id

    refs_root.mkdir(parents=True, exist_ok=True)
    refs_preview_root.mkdir(parents=True, exist_ok=True)
    res_root.mkdir(parents=True, exist_ok=True)
    res_preview_root.mkdir(parents=True, exist_ok=True)
    return project


def _get_db_session():
    # Flask-SQLAlchemy attaches db via app context; simplest import.
    from app.db import db

    return db.session


def create_project_and_save(shirt_filename: str) -> Project:
    project = create_project(shirt_filename)
    db = _get_db_session()
    db.add(project)
    db.commit()
    return project


def _save_uploaded_reference(project_id: str, file: FileStorage) -> Reference:
    app = current_app

    if not file or not file.filename:
        raise ValueError("Empty file upload")

    filename = secure_filename(file.filename)
    ext = Path(filename).suffix.lower()
    if not ext:
        ext = ".jpg"

    # allow only common image extensions
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError(f"Unsupported reference file type: {ext}")

    ref_id = str(uuid.uuid4())

    # detect mime quickly (best-effort)
    mime_type = file.mimetype or mimetypes.guess_type(filename)[0]

    refs_root = Path(app.config["REFERENCES_ORIGINAL_DIR"]) / project_id
    refs_preview_root = Path(app.config["REFERENCES_PREVIEW_DIR"]) / project_id
    refs_root.mkdir(parents=True, exist_ok=True)
    refs_preview_root.mkdir(parents=True, exist_ok=True)

    original_path = refs_root / f"{ref_id}{ext}"
    preview_path = refs_preview_root / f"{ref_id}.jpg"

    # stream to disk
    file.save(original_path)

    file_hash = compute_file_hash(original_path)
    make_preview_image(original_path, preview_path)

    original_rel_path = f"{project_id}/{original_path.name}"
    preview_rel_path = f"{project_id}/{preview_path.name}"

    ref = Reference(
        id=ref_id,
        project_id=project_id,
        original_rel_path=original_rel_path,
        preview_rel_path=preview_rel_path,
        file_hash=file_hash,
        mime_type=mime_type,
    )
    return ref


def add_references(project_id: str, files: List[FileStorage]) -> List[Reference]:
    from datetime import datetime

    app = current_app
    if not files:
        return []

    db = _get_db_session()
    project: Project | None = db.get(Project, project_id)  # type: ignore[arg-type]
    if not project:
        raise ValueError("Project not found")

    created: List[Reference] = []
    refs_original_root = Path(app.config["REFERENCES_ORIGINAL_DIR"])
    now = datetime.utcnow()

    for f in files:
        ref = _save_uploaded_reference(project_id, f)
        ref.prompt_started_at = now
        db.add(ref)
        created.append(ref)

    db.commit()

    # Асинхронная генерация промптов в фоне (параллельно по всем референсам)
    ref_ids = [r.id for r in created]
    flask_app = current_app._get_current_object()
    logger.info("Запуск фоновой генерации промптов для %d референсов: %s", len(ref_ids), ref_ids)

    def _process_with_context(ref_id: str):
        with flask_app.app_context():
            _process_prompt_for_ref(project_id, ref_id, refs_original_root)

    def _bg_generate_prompts() -> None:
        with ThreadPoolExecutor(max_workers=min(5, len(ref_ids))) as executor:
            futures = {executor.submit(_process_with_context, rid): rid for rid in ref_ids}
            for future in as_completed(futures):
                ref_id = futures[future]
                try:
                    future.result()
                    logger.info("Промпт получен для ref %s", ref_id)
                except Exception as e:  # noqa: BLE001
                    logger.exception("Ошибка генерации промпта для ref %s: %s", ref_id, e)

    threading.Thread(target=_bg_generate_prompts, daemon=True).start()

    return created


def _process_prompt_for_ref(
    project_id: str, ref_id: str, refs_original_root: Path
) -> None:
    """Генерирует промпт для одного референса и обновляет БД."""
    import time

    t0 = time.monotonic()
    logger.info("Начало генерации промпта для ref %s", ref_id)

    db = _get_db_session()
    ref: Reference | None = db.get(Reference, ref_id)  # type: ignore[arg-type]
    if not ref or ref.project_id != project_id:
        logger.warning("Ref %s не найден или не принадлежит проекту", ref_id)
        return
    original_path = refs_original_root / ref.original_rel_path
    try:
        prompt = generate_prompt_for_image(original_path)
        ref.generated_prompt = prompt
        ref.prompt_error = None
        elapsed = time.monotonic() - t0
        logger.info("OpenAI ответил для ref %s за %.1f сек, длина промпта: %d", ref_id, elapsed, len(prompt or ""))
    except Exception as e:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        logger.warning("OpenAI ошибка для ref %s после %.1f сек: %s", ref_id, elapsed, e)
        ref.generated_prompt = None
        ref.prompt_error = str(e)[:500]
    finally:
        db.add(ref)
        db.commit()


def regenerate_prompt_for_reference(project_id: str, reference_id: str) -> Reference | None:
    """Запускает повторную генерацию промпта для референса. Возвращает ref или None."""
    from datetime import datetime

    app = current_app
    db = _get_db_session()
    ref: Reference | None = Reference.query.filter_by(id=reference_id, project_id=project_id).first()
    if not ref:
        return None

    ref.generated_prompt = None
    ref.prompt_error = None
    ref.prompt_started_at = datetime.utcnow()
    db.add(ref)
    db.commit()

    refs_original_root = Path(app.config["REFERENCES_ORIGINAL_DIR"])
    flask_app = current_app._get_current_object()

    def _process_with_context():
        with flask_app.app_context():
            _process_prompt_for_ref(project_id, reference_id, refs_original_root)

    threading.Thread(target=_process_with_context, daemon=True).start()
    return ref


def delete_reference(project_id: str, reference_id: str) -> bool:
    """Удаляет референс и связанные файлы. Возвращает True при успехе."""
    app = current_app
    db = _get_db_session()
    ref: Reference | None = Reference.query.filter_by(id=reference_id, project_id=project_id).first()
    if not ref:
        logger.warning("delete_reference: ref %s not found in project %s", reference_id[:8], project_id[:8])
        return False

    # Удалить файлы с диска
    refs_original = Path(app.config["REFERENCES_ORIGINAL_DIR"])
    refs_preview = Path(app.config["REFERENCES_PREVIEW_DIR"])
    for base, rel in [(refs_original, ref.original_rel_path), (refs_preview, ref.preview_rel_path)]:
        if rel:
            p = base / rel
            if p.exists():
                try:
                    p.unlink()
                except OSError as e:
                    logger.warning("Не удалось удалить файл %s: %s", p, e)

    try:
        db.delete(ref)
        db.commit()
    except Exception as e:
        logger.exception("delete_reference: failed to delete ref %s: %s", reference_id[:8], e)
        db.rollback()
        raise
    return True


def list_references(project_id: str) -> List[Reference]:
    db = _get_db_session()
    refs = list(
        Reference.query.filter_by(project_id=project_id).order_by(Reference.created_at.desc()).all()
    )
    sync_refs_from_jobs(project_id, refs, db)
    return refs


def sync_refs_from_jobs(project_id: str, refs: List[Reference], db) -> None:
    """Синхронизирует result_* в Reference из GenerationJob для ref без результата.
    Также сбрасывает result_* если сохранённый результат от другого принта."""
    project = db.get(Project, project_id)
    if not project:
        return
    for ref in refs:
        job = (
            GenerationJob.query.filter_by(
                project_id=project_id, reference_id=ref.id, status="completed"
            )
            .filter(GenerationJob.result_preview_rel_path.isnot(None))
            .order_by(GenerationJob.created_at.desc())
            .first()
        )
        if not job or not job.result_preview_rel_path:
            # Сбросить result_* если ref указывает на результат от job с другим принтом
            ref_path = getattr(ref, "result_preview_rel_path", None)
            if ref_path:
                old_job = GenerationJob.query.filter_by(
                    project_id=project_id, reference_id=ref.id, status="completed",
                    result_preview_rel_path=ref_path,
                ).first()
                if old_job:
                    job_shirt = getattr(old_job, "shirt_filename", None)
                    if job_shirt is not None and job_shirt != project.shirt_filename:
                        ref.result_preview_rel_path = None
                        ref.result_original_rel_path = None
                        db.add(ref)
                        try:
                            db.commit()
                        except Exception:  # noqa: BLE001
                            db.rollback()
            continue
        # Не копировать результат, если job создан с другим принтом
        job_shirt = getattr(job, "shirt_filename", None)
        if job_shirt is not None and job_shirt != project.shirt_filename:
            if getattr(ref, "result_preview_rel_path", None):
                ref.result_preview_rel_path = None
                ref.result_original_rel_path = None
                db.add(ref)
                try:
                    db.commit()
                except Exception:  # noqa: BLE001
                    db.rollback()
            continue
        if getattr(ref, "result_preview_rel_path", None):
            continue
        try:
            ref.result_preview_rel_path = job.result_preview_rel_path
            ref.result_original_rel_path = job.result_original_rel_path
            db.add(ref)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()


def get_latest_result_for_reference(project_id: str, reference_id: str) -> dict | None:
    """Возвращает последний успешный результат для референса или None."""
    project = _get_db_session().get(Project, project_id)
    if not project:
        return None
    job = (
        GenerationJob.query.filter_by(
            project_id=project_id, reference_id=reference_id, status="completed"
        )
        .filter(GenerationJob.result_preview_rel_path.isnot(None))
        .order_by(GenerationJob.created_at.desc())
        .first()
    )
    if not job or not job.result_preview_rel_path:
        return None
    # Не показывать результат, если job создан с другим принтом
    job_shirt = getattr(job, "shirt_filename", None)
    if job_shirt is not None and job_shirt != project.shirt_filename:
        return None
    # Не показывать, если job имеет hash и файл принта был заменён (тот же filename, другое содержимое)
    job_hash = getattr(job, "shirt_file_hash", None)
    if job_hash is not None:
        shirt_path = Path(current_app.config["SHIRTS_DIR"]) / project.shirt_filename
        if shirt_path.exists():
            from app.utils.image_utils import compute_file_hash
            if compute_file_hash(shirt_path) != job_hash:
                return None
    return {
        "preview_url": f"/media/results/preview/{job.result_preview_rel_path}",
        "original_url": f"/media/results/original/{job.result_original_rel_path}",
    }


def _rel_to_media_url(media_base_path: str, rel_path: str) -> str:
    # rel_path is safe (we generate it from uuid)
    # media_base_path should be '/media/<kind>/<subdir>' in route.
    return f"{media_base_path}/{rel_path}"


def _use_kie_for_generation() -> bool:
    """Проверяет, настроен ли Kie.ai и можно ли его использовать."""
    key = current_app.config.get("KIE_API_KEY", "")
    return bool(key and not str(key).startswith("__PUT_"))


def generate_demo_results(project_id: str, options: dict | None = None) -> List[dict]:
    """
    Генерация результатов: Kie.ai Nano Banana Pro (если настроен) или демо-композит.
    """
    options = options or {}
    base_style = options.get("base_style", "base")
    torso_style = options.get("torso_style", "chest")
    model_filename = options.get("model") or ""

    app = current_app
    db = _get_db_session()

    project: Project | None = db.get(Project, project_id)  # type: ignore[arg-type]
    if not project:
        raise ValueError("Project not found")

    shirt_path = Path(app.config["SHIRTS_DIR"]) / project.shirt_filename
    if not shirt_path.exists():
        raise ValueError("Shirt file not found on server")
    shirt_file_hash = compute_file_hash(shirt_path)

    model_path = None
    if model_filename:
        from app.services.model_service import get_model_path
        model_path = get_model_path(model_filename)

    refs: List[Reference] = list(
        Reference.query.filter_by(project_id=project_id).order_by(Reference.created_at.asc()).all()
    )
    if not refs:
        return []

    jobs_out: List[dict] = []

    for ref in refs:
        # reuse only Kie-результаты (.png); старые демо (.jpg) — перегенерируем
        existing = (
            GenerationJob.query.filter_by(
                project_id=project_id, reference_id=ref.id, status="completed"
            )
            .order_by(GenerationJob.created_at.desc())
            .first()
        )
        is_kie_result = existing and existing.result_original_rel_path and existing.result_original_rel_path.endswith(".png")
        shirt_matches = (
            getattr(existing, "shirt_filename", None) is not None
            and existing.shirt_filename == project.shirt_filename
        )
        model_matches = (getattr(existing, "model_filename", None) or "") == (model_filename or "")
        hash_matches = (
            getattr(existing, "shirt_file_hash", None) is not None
            and existing.shirt_file_hash == shirt_file_hash
        )
        if existing and existing.result_preview_rel_path and is_kie_result and shirt_matches and model_matches and hash_matches:
            ref.result_preview_rel_path = existing.result_preview_rel_path
            ref.result_original_rel_path = existing.result_original_rel_path
            db.add(ref)
            db.commit()
            jobs_out.append(
                {
                    "job_id": existing.id,
                    "reference_id": ref.id,
                    "status": existing.status,
                    "preview_url": f"/media/results/preview/{existing.result_preview_rel_path}",
                    "original_url": f"/media/results/original/{existing.result_original_rel_path}",
                }
            )
            continue

        job_id = str(uuid.uuid4())
        job = GenerationJob(
            id=job_id,
            project_id=project_id,
            reference_id=ref.id,
            status="processing",
            shirt_filename=project.shirt_filename,
            model_filename=model_filename or None,
            shirt_file_hash=shirt_file_hash,
        )
        db.add(job)
        db.commit()

        try:
            reference_original_path = Path(app.config["REFERENCES_ORIGINAL_DIR"]) / ref.original_rel_path
            if not reference_original_path.exists():
                raise FileNotFoundError(f"Reference original missing: {reference_original_path}")

            results_root = Path(app.config["RESULTS_ORIGINAL_DIR"]) / project_id
            results_preview_root = Path(app.config["RESULTS_PREVIEW_DIR"]) / project_id
            results_root.mkdir(parents=True, exist_ok=True)
            results_preview_root.mkdir(parents=True, exist_ok=True)

            if not _use_kie_for_generation():
                raise ValueError(
                    "KIE_API_KEY не задан. Укажите ключ Kie.ai в .env (https://kie.ai/api-key)"
                )
            if not ref.generated_prompt:
                raise ValueError(
                    f"У референса {ref.id} нет сгенерированного промпта. "
                    "Дождитесь генерации или нажмите «Промпт» для перегенерации."
                )

            from app.services.kie_nanobanana_service import generate_image

            ref_path = Path(app.config["REFERENCES_ORIGINAL_DIR"]) / ref.original_rel_path
            out_original_path = results_root / f"{job_id}.png"
            out_preview_path = results_preview_root / f"{job_id}.jpg"

            model_prompt_text = app.config.get("KIE_MODEL_PROMPT_TEXT", "Use the provided reference image for the model appearance") if model_filename else ""
            generate_image(
                reference_prompt=ref.generated_prompt,
                shirt_path=shirt_path,
                reference_path=reference_original_path,
                base_style=base_style,
                torso_style=torso_style,
                model_path=model_path,
                model_name=model_prompt_text,
                out_path=out_original_path,
                project_id=project_id,
            )
            make_preview_image(out_original_path, out_preview_path)

            job.status = "completed"
            job.result_original_rel_path = f"{project_id}/{out_original_path.name}"
            job.result_preview_rel_path = f"{project_id}/{out_preview_path.name}"
            job.error_message = None
            ref.result_preview_rel_path = job.result_preview_rel_path
            ref.result_original_rel_path = job.result_original_rel_path
            db.add(job)
            db.add(ref)
            db.commit()

            jobs_out.append(
                {
                    "job_id": job.id,
                    "reference_id": ref.id,
                    "status": job.status,
                    "preview_url": f"/media/results/preview/{job.result_preview_rel_path}",
                    "original_url": f"/media/results/original/{job.result_original_rel_path}",
                }
            )
        except Exception as e:  # noqa: BLE001
            job.status = "failed"
            job.error_message = str(e)
            db.add(job)
            db.commit()
            jobs_out.append(
                {
                    "job_id": job.id,
                    "reference_id": ref.id,
                    "status": "failed",
                    "error_message": job.error_message,
                }
            )

    return jobs_out


def get_generation_preview(
    project_id: str,
    reference_id: str,
    base_style: str = "base",
    torso_style: str = "chest",
    model_filename: str = "",
) -> dict:
    """
    Возвращает превью задачи генерации: промпт и список файлов (без вызова Kie).
    """
    app = current_app
    db = _get_db_session()

    project: Project | None = db.get(Project, project_id)  # type: ignore[arg-type]
    if not project:
        raise ValueError("Project not found")

    ref: Reference | None = db.get(Reference, reference_id)  # type: ignore[arg-type]
    if not ref or ref.project_id != project_id:
        raise ValueError("Reference not found")

    reference_filename = Path(ref.original_rel_path).name

    from app.services.kie_nanobanana_service import build_generation_preview

    return build_generation_preview(
        reference_prompt=ref.generated_prompt or "",
        shirt_filename=project.shirt_filename,
        reference_filename=reference_filename,
        base_style=base_style,
        torso_style=torso_style,
        model_filename=model_filename,
    )


def generate_demo_results_for_reference(
    project_id: str,
    reference_id: str,
    options: dict | None = None,
    force: bool = False,
) -> dict:
    """
    Генерация результата для одного reference: Kie.ai или демо-композит.
    force=True создаёт новый job, а не переиспользует ранее completed-результат.
    """
    options = options or {}
    base_style = options.get("base_style", "base")
    torso_style = options.get("torso_style", "chest")
    model_filename = options.get("model") or ""

    app = current_app
    db = _get_db_session()

    project: Project | None = db.get(Project, project_id)  # type: ignore[arg-type]
    if not project:
        raise ValueError("Project not found")

    shirt_path = Path(app.config["SHIRTS_DIR"]) / project.shirt_filename
    if not shirt_path.exists():
        raise ValueError("Shirt file not found on server")
    shirt_file_hash = compute_file_hash(shirt_path)

    model_path = None
    if model_filename:
        from app.services.model_service import get_model_path
        model_path = get_model_path(model_filename)

    ref: Reference | None = db.get(Reference, reference_id)  # type: ignore[arg-type]
    if not ref or ref.project_id != project_id:
        raise ValueError("Reference not found")

    if not force:
        existing = (
            GenerationJob.query.filter_by(
                project_id=project_id, reference_id=reference_id, status="completed"
            )
            .order_by(GenerationJob.created_at.desc())
            .first()
        )
        is_kie_result = existing and existing.result_original_rel_path and existing.result_original_rel_path.endswith(".png")
        shirt_matches = (
            getattr(existing, "shirt_filename", None) is not None
            and existing.shirt_filename == project.shirt_filename
        )
        model_matches = (getattr(existing, "model_filename", None) or "") == (model_filename or "")
        hash_matches = (
            getattr(existing, "shirt_file_hash", None) is not None
            and existing.shirt_file_hash == shirt_file_hash
        )
        if existing and existing.result_preview_rel_path and existing.result_original_rel_path and is_kie_result and shirt_matches and model_matches and hash_matches:
            ref.result_preview_rel_path = existing.result_preview_rel_path
            ref.result_original_rel_path = existing.result_original_rel_path
            db.add(ref)
            db.commit()
            return {
                "job_id": existing.id,
                "reference_id": reference_id,
                "status": existing.status,
                "preview_url": f"/media/results/preview/{existing.result_preview_rel_path}",
                "original_url": f"/media/results/original/{existing.result_original_rel_path}",
            }

    job_id = str(uuid.uuid4())
    job = GenerationJob(
        id=job_id,
        project_id=project_id,
        reference_id=reference_id,
        status="processing",
        shirt_filename=project.shirt_filename,
        model_filename=model_filename or None,
        shirt_file_hash=shirt_file_hash,
    )
    db.add(job)
    db.commit()

    try:
        reference_original_path = Path(app.config["REFERENCES_ORIGINAL_DIR"]) / ref.original_rel_path
        if not reference_original_path.exists():
            raise FileNotFoundError(f"Reference original missing: {reference_original_path}")

        results_root = Path(app.config["RESULTS_ORIGINAL_DIR"]) / project_id
        results_preview_root = Path(app.config["RESULTS_PREVIEW_DIR"]) / project_id
        results_root.mkdir(parents=True, exist_ok=True)
        results_preview_root.mkdir(parents=True, exist_ok=True)

        if not _use_kie_for_generation():
            raise ValueError(
                "KIE_API_KEY не задан. Укажите ключ Kie.ai в .env (https://kie.ai/api-key)"
            )
        if not ref.generated_prompt:
            raise ValueError(
                f"У референса {reference_id} нет сгенерированного промпта. "
                "Дождитесь генерации или нажмите «Промпт» для перегенерации."
            )

        from app.services.kie_nanobanana_service import generate_image

        shirt_path = Path(app.config["SHIRTS_DIR"]) / project.shirt_filename
        out_original_path = results_root / f"{job_id}.png"
        out_preview_path = results_preview_root / f"{job_id}.jpg"

        model_prompt_text = app.config.get("KIE_MODEL_PROMPT_TEXT", "Use the provided reference image for the model appearance") if model_filename else ""
        generate_image(
            reference_prompt=ref.generated_prompt,
            shirt_path=shirt_path,
            reference_path=reference_original_path,
            base_style=base_style,
            torso_style=torso_style,
            model_path=model_path,
            model_name=model_prompt_text,
            out_path=out_original_path,
            project_id=project_id,
        )
        make_preview_image(out_original_path, out_preview_path)

        job.status = "completed"
        job.result_original_rel_path = f"{project_id}/{out_original_path.name}"
        job.result_preview_rel_path = f"{project_id}/{out_preview_path.name}"
        job.error_message = None
        ref.result_preview_rel_path = job.result_preview_rel_path
        ref.result_original_rel_path = job.result_original_rel_path
        db.add(job)
        db.add(ref)
        db.commit()

        return {
            "job_id": job.id,
            "reference_id": reference_id,
            "status": job.status,
            "preview_url": f"/media/results/preview/{job.result_preview_rel_path}",
            "original_url": f"/media/results/original/{job.result_original_rel_path}",
        }
    except Exception as e:  # noqa: BLE001
        job.status = "failed"
        job.error_message = str(e)
        db.add(job)
        db.commit()

        return {
            "job_id": job.id,
            "reference_id": reference_id,
            "status": "failed",
            "error_message": job.error_message,
        }


def delete_video_generation(project_id: str, video_id: str) -> bool:
    """Удаляет генерацию видео. Возвращает True при успехе."""
    db = _get_db_session()
    v: VideoGeneration | None = VideoGeneration.query.filter_by(
        id=video_id, project_id=project_id
    ).first()
    if not v:
        logger.warning("delete_video_generation: not found id=%s project=%s", video_id[:16], project_id[:16])
        return False
    db.delete(v)
    db.commit()
    return True


def list_video_generations(project_id: str) -> List[dict]:
    """Список генераций видео по проекту."""
    db = _get_db_session()
    vgens = (
        VideoGeneration.query.filter_by(project_id=project_id)
        .order_by(VideoGeneration.created_at.asc())
        .all()
    )
    # Пометить «осиротевшие» задачи (processing без kie_task_id, старше 15 мин)
    now = datetime.now(timezone.utc)
    for v in vgens:
        if v.status == "processing" and not v.kie_task_id and v.created_at:
            created = v.created_at if v.created_at.tzinfo else v.created_at.replace(tzinfo=timezone.utc)
            delta = (now - created).total_seconds()
            if delta > 900:  # 15 min
                v.status = "failed"
                v.error_message = "Задача прервана (перезапуск сервера или ошибка)"
                logger.info("video-gen %s: marked stale (no kie_task_id, age=%.0fs)", v.id[:8], delta)
    if any(v.status == "failed" for v in vgens):
        db.commit()
    return [
        {
            "id": v.id,
            "source_reference_id": v.source_reference_id,
            "status": v.status,
            "video_url": v.video_url,
            "error_message": v.error_message,
            "kie_task_id": v.kie_task_id,
            "created_at": (v.created_at.isoformat() + "Z") if v.created_at else None,
        }
        for v in vgens
    ]


def generate_video_from_reference(project_id: str, reference_id: str) -> dict:
    """
    Запускает генерацию видео из результата референса через Kie grok-imagine/image-to-video.
    Создаёт VideoGeneration, отправляет запрос в Kie, опрашивает в фоне.
    """
    app = current_app
    db = _get_db_session()

    project: Project | None = db.get(Project, project_id)  # type: ignore[arg-type]
    if not project:
        raise ValueError("Project not found")
    ref: Reference | None = db.get(Reference, reference_id)  # type: ignore[arg-type]
    if not ref or ref.project_id != project_id:
        raise ValueError("Reference not found")

    result_rel_path = ref.result_original_rel_path
    if not result_rel_path:
        job = (
            GenerationJob.query.filter_by(
                project_id=project_id, reference_id=reference_id, status="completed"
            )
            .filter(GenerationJob.result_original_rel_path.isnot(None))
            .order_by(GenerationJob.created_at.desc())
            .first()
        )
        if job:
            result_rel_path = job.result_original_rel_path
    if not result_rel_path:
        raise ValueError("Нет сгенерированного результата для создания видео")

    results_dir = Path(app.config["RESULTS_ORIGINAL_DIR"])
    result_file_path = results_dir / result_rel_path
    if not result_file_path.exists():
        raise ValueError("Файл результата не найден")

    video_id = str(uuid.uuid4())
    vgen = VideoGeneration(
        id=video_id,
        project_id=project_id,
        source_reference_id=reference_id,
        status="processing",
    )
    db.add(vgen)
    db.commit()

    # Захватываем app в основном потоке (в request context)
    flask_app = current_app._get_current_object()

    def _run_video_generation():
        with flask_app.app_context(), flask_app.test_request_context():
            from app.services.kie_grok_video_service import create_video_task, poll_video_task
            from app.services.kie_nanobanana_service import _upload_file_base64

            db_session = _get_db_session()
            v = db_session.get(VideoGeneration, video_id)  # type: ignore[arg-type]
            if not v or v.status != "processing":
                logger.warning("Video gen %s: skip (v=%s status=%s)", video_id[:8], "ok" if v else "None", v.status if v else "n/a")
                return
            try:
                # Загружаем изображение в Kie CDN — createTask вернёт taskId за секунды
                # (вместо ожидания загрузки с нашего сервера)
                logger.info("Video gen %s: uploading image to Kie...", video_id[:8])
                image_url = _upload_file_base64(
                    result_file_path,
                    upload_path="photomaker/video",
                    file_name=f"video_src_{video_id[:8]}{result_file_path.suffix}",
                )
                logger.info("Video gen %s: calling Kie createTask image_url=%s", video_id[:8], image_url[:60])
                task_id = create_video_task(
                    image_url=image_url,
                    mode="normal",
                    duration="6",
                    resolution="720p",
                )
                logger.info("Video gen %s: Kie task_id=%s", video_id[:8], task_id[:24] if task_id else None)
                v.kie_task_id = task_id
                db_session.commit()
                result = poll_video_task(task_id, max_wait_sec=600, interval_sec=5.0)
                urls = result.get("resultUrls", [])
                if urls:
                    v.video_url = urls[0]
                    v.status = "completed"
                else:
                    v.status = "failed"
                    v.error_message = "No video URL in Kie response"
            except Exception as e:
                logger.exception("Video gen %s: Kie failed: %s", video_id[:8], e)
                v.status = "failed"
                v.error_message = str(e)
            finally:
                try:
                    db_session.commit()
                except Exception as ce:
                    logger.exception("Video gen %s: commit failed: %s", video_id[:8], ce)

    threading.Thread(target=_run_video_generation, daemon=True).start()

    return {
        "id": video_id,
        "source_reference_id": reference_id,
        "status": "processing",
    }

