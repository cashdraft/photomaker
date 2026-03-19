from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, current_app, jsonify, request

import shutil
from app.models import GenerationJob, Project, Reference
from app.services.project_service import (
    add_references,
    create_project_and_save,
    generate_demo_results,
    generate_demo_results_for_reference,
    get_latest_result_for_reference,
    list_references,
)
from app.services.shirt_service import list_shirts
from app.services.model_service import list_models
from app.utils.image_utils import make_preview_image


bp = Blueprint("api", __name__, url_prefix="/api")


def _ref_to_json(ref: Reference, project_id: str | None = None) -> Dict[str, Any]:
    prompt_started = getattr(ref, "prompt_started_at", None)
    out = {
        "id": ref.id,
        "preview_url": f"/media/references/preview/{ref.preview_rel_path}",
        "original_url": f"/media/references/original/{ref.original_rel_path}",
        "mime_type": ref.mime_type,
        "file_hash": ref.file_hash,
        "generated_prompt": ref.generated_prompt,
        "prompt_error": ref.prompt_error,
        "created_at": (ref.created_at.isoformat() + "Z") if ref.created_at else None,
        "prompt_started_at": (prompt_started.isoformat() + "Z") if prompt_started else None,
    }
    if project_id:
        result = get_latest_result_for_reference(project_id, ref.id)
        if result:
            out["result_preview_url"] = result["preview_url"]
            out["result_original_url"] = result["original_url"]
    return out


@bp.get("/models")
def models_list():
    items = list_models()
    return jsonify({"items": items})


@bp.get("/shirts")
def shirts_search():
    q = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", "6"))
    items, total = list_shirts(query=q, limit=limit)
    return jsonify({"items": items, "total": total})


@bp.post("/projects")
def create_project():
    payload = request.get_json(silent=True) or {}
    shirt_filename = payload.get("shirt_filename") or payload.get("filename")
    if not shirt_filename:
        return jsonify({"error": "Missing shirt_filename"}), 400

    try:
        project: Project = create_project_and_save(shirt_filename=shirt_filename)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"project_id": project.id})


def _project_status(project_id: str) -> str:
    # "новый" -> нет задач
    # "генерируется" -> есть processing/queued
    # "готово" -> есть completed и нет processing/queued
    # "ошибка" -> есть failed
    jobs = GenerationJob.query.filter_by(project_id=project_id).all()
    if not jobs:
        return "новый"

    if any(j.status in {"queued", "processing", "submitted", "retrying"} for j in jobs):
        return "генерируется"

    if any(j.status == "failed" for j in jobs):
        return "ошибка"

    if all(j.status == "completed" for j in jobs):
        return "готово"

    # на случай будущих статусов от провайдера
    return "в процессе"


@bp.get("/projects")
def projects_list():
    # В демо-режиме нет аутентификации, поэтому показываем все проекты.
    projects = Project.query.order_by(Project.created_at.desc()).all()
    base_shirts_dir = Path(current_app.config["SHIRTS_DIR"])
    base_shirts_preview_dir = Path(current_app.config["SHIRTS_PREVIEW_DIR"])

    items = []
    for p in projects:
        # ensure preview exists (best-effort)
        shirt_src = base_shirts_dir / p.shirt_filename
        preview_name = f"{shirt_src.stem}.jpg"
        shirt_preview_path = base_shirts_preview_dir / preview_name
        try:
            if shirt_src.exists() and not shirt_preview_path.exists():
                make_preview_image(shirt_src, shirt_preview_path, force=True, max_size=(180, 180))
        except Exception:
            # Не ломаем список, если превью не удалось создать
            pass

        refs_count = Reference.query.filter_by(project_id=p.id).count()
        items.append(
            {
                "project_id": p.id,
                "shirt_filename": p.shirt_filename,
                "shirt_preview_url": f"/media/shirts/preview/{preview_name}",
                "references_count": refs_count,
                "status": _project_status(p.id),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
        )

    return jsonify({"items": items})


@bp.delete("/projects/<project_id>")
def projects_delete(project_id: str):
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # filesystem cleanup (best-effort)
    refs_original_root = Path(current_app.config["REFERENCES_ORIGINAL_DIR"]) / project_id
    refs_preview_root = Path(current_app.config["REFERENCES_PREVIEW_DIR"]) / project_id
    results_original_root = Path(current_app.config["RESULTS_ORIGINAL_DIR"]) / project_id
    results_preview_root = Path(current_app.config["RESULTS_PREVIEW_DIR"]) / project_id

    try:
        shutil.rmtree(refs_original_root, ignore_errors=True)
        shutil.rmtree(refs_preview_root, ignore_errors=True)
        shutil.rmtree(results_original_root, ignore_errors=True)
        shutil.rmtree(results_preview_root, ignore_errors=True)
    except Exception:
        pass

    # DB cleanup
    GenerationJob.query.filter_by(project_id=project_id).delete()
    Reference.query.filter_by(project_id=project_id).delete()
    Project.query.filter_by(id=project_id).delete()
    from app.db import db

    db.session.commit()

    return jsonify({"ok": True})


@bp.get("/projects/<project_id>/references")
def references_list(project_id: str):
    refs = list_references(project_id)
    return jsonify({"items": [_ref_to_json(r, project_id) for r in refs]})


@bp.post("/projects/<project_id>/references")
def references_upload(project_id: str):
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    try:
        refs = add_references(project_id=project_id, files=files)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"items": [_ref_to_json(r, project_id) for r in refs]})


@bp.post("/projects/<project_id>/generate")
def projects_generate(project_id: str):
    try:
        payload = request.get_json(silent=True) or {}
        jobs_out: List[dict] = generate_demo_results(
            project_id=project_id,
            options={
                "base_style": payload.get("base_style", "base"),
                "torso_style": payload.get("torso_style", "chest"),
                "model": payload.get("model") or "",
            },
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"items": jobs_out})


@bp.post("/projects/<project_id>/references/<reference_id>/regenerate-prompt")
def references_regenerate_prompt(project_id: str, reference_id: str):
    from app.services.project_service import regenerate_prompt_for_reference

    try:
        ref = regenerate_prompt_for_reference(project_id, reference_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if not ref:
        return jsonify({"error": "Reference not found"}), 404
    return jsonify(_ref_to_json(ref, project_id))


@bp.post("/projects/<project_id>/references/<reference_id>/regenerate")
def references_regenerate(project_id: str, reference_id: str):
    try:
        payload = request.get_json(silent=True) or {}
        job_out = generate_demo_results_for_reference(
            project_id=project_id,
            reference_id=reference_id,
            force=True,
            options={
                "base_style": payload.get("base_style", "base"),
                "torso_style": payload.get("torso_style", "chest"),
                "model": payload.get("model") or "",
            },
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400

    return jsonify(job_out)

