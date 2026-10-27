"""Application configuration with transparent, documented defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
EPISODES_DIR = DATA_DIR / "episodes"


class Settings(BaseSettings):
    """Runtime settings. AWS fields are optional placeholders only."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "WorldTrace AI"
    app_version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = DATA_DIR
    episodes_dir: Path = EPISODES_DIR

    # Video geometry
    frame_width: int = 640
    frame_height: int = 360
    fps: int = 15

    # HSV range for a vivid green object (OpenCV H in 0..179)
    hsv_lower: Tuple[int, int, int] = (35, 80, 80)
    hsv_upper: Tuple[int, int, int] = (85, 255, 255)
    min_contour_area: float = 120.0

    # Zone rectangles as fractions of frame (x, y, w, h)
    source_zone: Tuple[float, float, float, float] = (0.02, 0.25, 0.22, 0.50)
    destination_zone: Tuple[float, float, float, float] = (0.76, 0.25, 0.22, 0.50)

    # Decision thresholds
    settle_frames_required: int = 8
    min_visibility_ratio: float = 0.55
    min_tracking_coverage: float = 0.45
    max_occlusion_gap_frames: int = 12
    min_transit_frames: int = 3

    # Optional AWS archival — NOT configured or tested by default
    aws_s3_enabled: bool = False
    aws_s3_bucket: str = ""
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""


settings = Settings()
EPISODES_DIR.mkdir(parents=True, exist_ok=True)
