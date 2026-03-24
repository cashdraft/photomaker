from __future__ import annotations

from datetime import datetime

from .db import db


class Project(db.Model):
    __tablename__ = "projects"

    # uuid4 as string: 36 chars (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
    id = db.Column(db.String(36), primary_key=True)

    shirt_filename = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    references = db.relationship(
        "Reference", backref="project", cascade="all, delete-orphan", lazy=True
    )


class Reference(db.Model):
    __tablename__ = "references"

    id = db.Column(db.String(36), primary_key=True)

    project_id = db.Column(
        db.String(36), db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Stored relative paths under data/<kind>/<subdir>
    original_rel_path = db.Column(db.String(512), nullable=False)
    preview_rel_path = db.Column(db.String(512), nullable=False)

    file_hash = db.Column(db.String(64), nullable=False, index=True)
    mime_type = db.Column(db.String(128), nullable=True)

    # Промпт, сгенерированный OpenAI по картинке (мастерпромпт + изображение)
    generated_prompt = db.Column(db.Text, nullable=True)
    prompt_error = db.Column(db.Text, nullable=True)
    prompt_started_at = db.Column(db.DateTime, nullable=True)  # когда последний раз запускали генерацию промпта

    # Последний результат генерации (копия из GenerationJob для надёжного отображения)
    result_preview_rel_path = db.Column(db.String(512), nullable=True)
    result_original_rel_path = db.Column(db.String(512), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class GenerationJob(db.Model):
    __tablename__ = "generation_jobs"

    id = db.Column(db.String(36), primary_key=True)

    project_id = db.Column(
        db.String(36), db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reference_id = db.Column(
        db.String(36), db.ForeignKey("references.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Какой принт и модель использовались (для проверки при переиспользовании)
    shirt_filename = db.Column(db.String(255), nullable=True)
    model_filename = db.Column(db.String(255), nullable=True)
    # SHA256 хеш файла принта — если файл заменён, результат не показываем
    shirt_file_hash = db.Column(db.String(64), nullable=True)

    status = db.Column(db.String(32), nullable=False, default="queued", index=True)
    error_message = db.Column(db.Text, nullable=True)

    # output relative paths under data/results
    result_original_rel_path = db.Column(db.String(512), nullable=True)
    result_preview_rel_path = db.Column(db.String(512), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class VideoGeneration(db.Model):
    """Генерация видео из сгенерированной картинки через Kie grok-imagine/image-to-video."""
    __tablename__ = "video_generations"

    id = db.Column(db.String(36), primary_key=True)

    project_id = db.Column(
        db.String(36), db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_reference_id = db.Column(
        db.String(36), db.ForeignKey("references.id", ondelete="CASCADE"), nullable=False, index=True
    )

    kie_task_id = db.Column(db.String(128), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default="processing", index=True)
    video_url = db.Column(db.String(1024), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

