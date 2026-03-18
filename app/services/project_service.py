from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import IO, List, Tuple

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.models import GenerationJob, Project, Reference
from app.utils.image_utils import (
    compute_file_hash,
    make_demo_composite,
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
    app = current_app
    if not files:
        return []

    db = _get_db_session()
    project: Project | None = db.get(Project, project_id)  # type: ignore[arg-type]
    if not project:
        raise ValueError("Project not found")

    created: List[Reference] = []
    for f in files:
        ref = _save_uploaded_reference(project_id, f)
        db.add(ref)
        created.append(ref)

    db.commit()
    return created


def list_references(project_id: str) -> List[Reference]:
    db = _get_db_session()
    return list(
        Reference.query.filter_by(project_id=project_id).order_by(Reference.created_at.desc()).all()
    )


def _rel_to_media_url(media_base_path: str, rel_path: str) -> str:
    # rel_path is safe (we generate it from uuid)
    # media_base_path should be '/media/<kind>/<subdir>' in route.
    return f"{media_base_path}/{rel_path}"


def generate_demo_results(project_id: str, options: dict | None = None) -> List[dict]:
    """
    Демо-генерация: накладываем уменьшенный принт (shirt image) на низ изображения-референса.
    """
    # options зарезервированы под реальный prompt/NanoBanana,
    # в демо-режиме они пока не влияют на итог.
    _ = options
    app = current_app
    db = _get_db_session()

    project: Project | None = db.get(Project, project_id)  # type: ignore[arg-type]
    if not project:
        raise ValueError("Project not found")

    shirt_path = Path(app.config["SHIRTS_DIR"]) / project.shirt_filename
    if not shirt_path.exists():
        raise ValueError("Shirt file not found on server")

    refs: List[Reference] = list(
        Reference.query.filter_by(project_id=project_id).order_by(Reference.created_at.asc()).all()
    )
    if not refs:
        return []

    jobs_out: List[dict] = []

    for ref in refs:
        # reuse latest completed job (if any)
        existing = (
            GenerationJob.query.filter_by(
                project_id=project_id, reference_id=ref.id, status="completed"
            )
            .order_by(GenerationJob.created_at.desc())
            .first()
        )
        if existing and existing.result_preview_rel_path:
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
            id=job_id, project_id=project_id, reference_id=ref.id, status="processing"
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

            out_original_path = results_root / f"{job_id}.jpg"
            out_preview_path = results_preview_root / f"{job_id}.jpg"

            make_demo_composite(
                reference_path=reference_original_path,
                shirt_path=shirt_path,
                out_original_path=out_original_path,
                out_preview_path=out_preview_path,
            )

            job.status = "completed"
            job.result_original_rel_path = f"{project_id}/{out_original_path.name}"
            job.result_preview_rel_path = f"{project_id}/{out_preview_path.name}"
            job.error_message = None
            db.add(job)
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


def generate_demo_results_for_reference(
    project_id: str,
    reference_id: str,
    options: dict | None = None,
    force: bool = False,
) -> dict:
    """
    Демо-генерация только для одного reference.

    force=True создаёт новый job, а не переиспользует ранее completed-результат.
    """
    # options зарезервированы под реальный prompt/NanoBanana,
    # в демо-режиме они пока не влияют на итог.
    _ = options

    app = current_app
    db = _get_db_session()

    project: Project | None = db.get(Project, project_id)  # type: ignore[arg-type]
    if not project:
        raise ValueError("Project not found")

    shirt_path = Path(app.config["SHIRTS_DIR"]) / project.shirt_filename
    if not shirt_path.exists():
        raise ValueError("Shirt file not found on server")

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
        if existing and existing.result_preview_rel_path and existing.result_original_rel_path:
            return {
                "job_id": existing.id,
                "reference_id": reference_id,
                "status": existing.status,
                "preview_url": f"/media/results/preview/{existing.result_preview_rel_path}",
                "original_url": f"/media/results/original/{existing.result_original_rel_path}",
            }

    job_id = str(uuid.uuid4())
    job = GenerationJob(
        id=job_id, project_id=project_id, reference_id=reference_id, status="processing"
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

        out_original_path = results_root / f"{job_id}.jpg"
        out_preview_path = results_preview_root / f"{job_id}.jpg"

        make_demo_composite(
            reference_path=reference_original_path,
            shirt_path=shirt_path,
            out_original_path=out_original_path,
            out_preview_path=out_preview_path,
        )

        job.status = "completed"
        job.result_original_rel_path = f"{project_id}/{out_original_path.name}"
        job.result_preview_rel_path = f"{project_id}/{out_preview_path.name}"
        job.error_message = None
        db.add(job)
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

