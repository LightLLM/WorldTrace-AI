"""REST API for WorldTrace AI."""

from __future__ import annotations

from pathlib import Path

import cv2
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app import __version__
from app.core.config import settings
from app.core.models import ReviewRequest
from app.services.episode import episode_service

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "opencv": cv2.__version__,
        "python_compatible": True,
    }


@router.get("/config")
def get_config():
    return {
        "app_name": settings.app_name,
        "frame_width": settings.frame_width,
        "frame_height": settings.frame_height,
        "fps": settings.fps,
        "hsv_lower": settings.hsv_lower,
        "hsv_upper": settings.hsv_upper,
        "source_zone": settings.source_zone,
        "destination_zone": settings.destination_zone,
        "settle_frames_required": settings.settle_frames_required,
        "min_visibility_ratio": settings.min_visibility_ratio,
        "min_tracking_coverage": settings.min_tracking_coverage,
        "max_occlusion_gap_frames": settings.max_occlusion_gap_frames,
        "aws_s3_enabled": settings.aws_s3_enabled,
        "aws_note": "AWS S3 archival is optional and unverified unless explicitly configured and tested.",
        "quality_formula": (
            "100*(0.20*started_in_source + 0.15*left_source + 0.15*transit_observed + "
            "0.20*reached_destination + 0.15*settled_in_destination + "
            "0.10*visibility_ratio + 0.05*min(1, tracking_coverage))"
        ),
        "scenarios": ["successful", "incomplete", "occluded"],
    }


@router.post("/scenarios/{scenario_name}")
def run_scenario(scenario_name: str):
    return episode_service.run_scenario(scenario_name)


@router.post("/episodes/upload")
async def upload_episode(file: UploadFile = File(...)):
    episode_id = await episode_service.save_upload(file)
    return {"episode_id": episode_id, "status": "uploaded"}


@router.post("/episodes/{episode_id}/process")
def process_episode(episode_id: str):
    return episode_service.process_episode(episode_id)


@router.get("/episodes")
def list_episodes():
    return episode_service.list_episodes()


@router.get("/episodes/{episode_id}")
def get_episode(episode_id: str):
    return episode_service.get_episode(episode_id)


@router.get("/episodes/{episode_id}/trajectory")
def get_trajectory(episode_id: str):
    return {"episode_id": episode_id, "points": episode_service.trajectory_points(episode_id)}


@router.post("/episodes/{episode_id}/review")
def review_episode(episode_id: str, body: ReviewRequest):
    return episode_service.review_episode(episode_id, body)


@router.get("/episodes/{episode_id}/download")
def download_episode(episode_id: str):
    zip_path = episode_service.download_zip(episode_id)
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )
