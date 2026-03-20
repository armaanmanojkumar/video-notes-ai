import shutil
from pathlib import Path


def ensure_frontend_served():
    project_root = Path(__file__).resolve().parent.parent.parent
    src = project_root / "frontend" / "index.html"
    dist_dir = project_root / "frontend" / "dist"
    if src.exists():
        dist_dir.mkdir(parents=True, exist_ok=True)
        dest = dist_dir / "index.html"
        if not dest.exists() or src.stat().st_mtime > dest.stat().st_mtime:
            shutil.copy2(src, dest)
