#!/usr/bin/env python3
"""
Диагностика: какой принт уходит в Kie при генерации.
Запуск: python scripts/debug_shirt_flow.py <project_id>
"""
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.utils.image_utils import compute_file_hash

def main():
    if len(sys.argv) < 2:
        print("Использование: python scripts/debug_shirt_flow.py <project_id>")
        print("Пример: python scripts/debug_shirt_flow.py f856b7a5-c159-405a-99ec-95ff58877f7c")
        sys.exit(1)
    
    project_id = sys.argv[1]
    app = create_app()
    
    with app.app_context():
        from app.models import Project, Reference, GenerationJob
        from app.db import db
        
        project = db.session.get(Project, project_id)
        if not project:
            print(f"Проект {project_id} не найден")
            sys.exit(1)
        
        shirt_path = Path(app.config["SHIRTS_DIR"]) / project.shirt_filename
        print("=" * 60)
        print("ПРОЕКТ:", project_id)
        print("shirt_filename (из БД):", project.shirt_filename)
        print("Полный путь:", shirt_path)
        print("Файл существует:", shirt_path.exists())
        if shirt_path.exists():
            st = shirt_path.stat()
            h = compute_file_hash(shirt_path)
            print("Размер (bytes):", st.st_size)
            print("Hash (SHA256):", h[:32] + "...")
        print()
        
        # Последние jobs по проекту
        jobs = (GenerationJob.query.filter_by(project_id=project_id, status="completed")
                .order_by(GenerationJob.created_at.desc()).limit(5).all())
        print("Последние 5 completed jobs:")
        for j in jobs:
            j_shirt = getattr(j, "shirt_filename", "?")
            j_hash = getattr(j, "shirt_file_hash", "?")
            match = ""
            if shirt_path.exists() and j_hash and j_hash != "?":
                curr_h = compute_file_hash(shirt_path)
                match = " [совпадает]" if curr_h == j_hash else " [НЕ СОВПАДАЕТ!]"
            print(f"  job {j.id[:8]}... shirt={j_shirt} hash={j_hash[:16] if j_hash else '?'}...{match}")
        print()
        
        # Все проекты с их shirt и hash для сравнения
        print("Все проекты (для сравнения):")
        for p in Project.query.all():
            sp = Path(app.config["SHIRTS_DIR"]) / p.shirt_filename
            h = compute_file_hash(sp)[:16] + "..." if sp.exists() else "N/A"
            print(f"  {p.id[:8]}... shirt={p.shirt_filename} hash={h}")

if __name__ == "__main__":
    main()
