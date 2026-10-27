from pathlib import Path

from app.core.config import settings
from app.services.synthetic import (
    generate_incomplete,
    generate_occluded,
    generate_successful,
)
from app.vision.tracker import track_video


def test_synthetic_video_creation(tmp_path):
    path = tmp_path / "ok.mp4"
    generate_successful(path, settings, n_frames=30)
    assert path.exists()
    assert path.stat().st_size > 1000


def test_object_tracking(tmp_path):
    original = tmp_path / "original.mp4"
    annotated = tmp_path / "annotated.mp4"
    generate_successful(original, settings, n_frames=40)
    observations = track_video(original, annotated, settings)
    assert len(observations) > 0
    visible = [o for o in observations if o.visible]
    assert len(visible) > 10
    assert annotated.exists()
    assert all(o.nx is not None for o in visible)
