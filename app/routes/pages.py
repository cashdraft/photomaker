from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, render_template

from app.db import db as db_handle
from app.models import Project
from app.services.project_service import get_latest_result_for_reference, list_references
from app.utils.image_utils import make_preview_image


bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/projects/<project_id>")
def project_generation(project_id: str):
    project: Project | None = db_handle.session.get(Project, project_id)  # type: ignore[arg-type]
    if not project:
        return render_template(
            "project_generation_not_found.html", project_id=project_id
        ), 404

    # Ensure shirt preview exists
    shirt_src = Path(current_app.config["SHIRTS_DIR"]) / project.shirt_filename
    preview_name = f"{shirt_src.stem}.jpg"
    shirt_preview_path = Path(current_app.config["SHIRTS_PREVIEW_DIR"]) / preview_name
    if shirt_src.exists():
        make_preview_image(shirt_src, shirt_preview_path)

    shirt_preview_url = f"/media/shirts/preview/{preview_name}"

    refs = list_references(project_id=project_id)
    references = []
    for r in refs:
        ref_data = {
            "id": r.id,
            "preview_url": f"/media/references/preview/{r.preview_rel_path}",
            "original_url": f"/media/references/original/{r.original_rel_path}",
            "generated_prompt": r.generated_prompt,
            "prompt_error": r.prompt_error,
            "created_at": (r.created_at.isoformat() + "Z") if r.created_at else None,
            "prompt_started_at": (r.prompt_started_at.isoformat() + "Z") if getattr(r, "prompt_started_at", None) else None,
        }
        result = get_latest_result_for_reference(project_id, r.id)
        if result:
            ref_data["result_preview_url"] = result["preview_url"]
            ref_data["result_original_url"] = result["original_url"]
        references.append(ref_data)

    return render_template(
        "project_generation.html",
        project={"id": project.id, "shirt_filename": project.shirt_filename},
        shirt_preview_url=shirt_preview_url,
        references=references,
    )

