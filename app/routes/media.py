from __future__ import annotations

from flask import Blueprint, current_app, send_from_directory


bp = Blueprint("media", __name__, url_prefix="/media")


def _send(directory_key: str, path: str):
    directory = current_app.config[directory_key]
    return send_from_directory(directory, path)


@bp.get("/shirts/preview/<path:filename>")
def shirts_preview(filename: str):
    return _send("SHIRTS_PREVIEW_DIR", filename)


@bp.get("/shirts/original/<path:filename>")
def shirts_original(filename: str):
    return _send("SHIRTS_DIR", filename)


@bp.get("/references/preview/<path:rel_path>")
def references_preview(rel_path: str):
    return _send("REFERENCES_PREVIEW_DIR", rel_path)


@bp.get("/references/original/<path:rel_path>")
def references_original(rel_path: str):
    return _send("REFERENCES_ORIGINAL_DIR", rel_path)


@bp.get("/results/preview/<path:rel_path>")
def results_preview(rel_path: str):
    return _send("RESULTS_PREVIEW_DIR", rel_path)


@bp.get("/results/original/<path:rel_path>")
def results_original(rel_path: str):
    return _send("RESULTS_ORIGINAL_DIR", rel_path)


@bp.get("/models/<path:filename>")
def models_file(filename: str):
    return _send("MODELS_DIR", filename)

