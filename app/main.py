"""WorldTrace AI FastAPI application entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = BASE_DIR / "templates"
STATIC = BASE_DIR / "static"

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Research prototype for auditable warehouse transfer capture using OpenCV. "
        "Not production-ready. Not a claim of real warehouse validation."
    ),
)

app.include_router(router)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def home():
    return FileResponse(TEMPLATES / "index.html")


@app.get("/media/{episode_id}/{filename}")
def media(episode_id: str, filename: str):
    allowed = {"original.mp4", "annotated.mp4"}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="Media not found.")
    path = settings.episodes_dir / episode_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Media not found.")
    return FileResponse(path, media_type="video/mp4")
