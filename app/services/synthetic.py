"""Deterministic synthetic transfer videos generated entirely in code."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

from app.core.config import Settings, settings
from app.core.models import ScenarioName
from app.vision.zones import fraction_to_pixels


def _zone_centers(cfg: Settings) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    sx, sy, sw, sh = cfg.source_zone
    dx, dy, dw, dh = cfg.destination_zone
    source_c = ((sx + sw / 2) * cfg.frame_width, (sy + sh / 2) * cfg.frame_height)
    dest_c = ((dx + dw / 2) * cfg.frame_width, (dy + dh / 2) * cfg.frame_height)
    return source_c, dest_c


def _draw_scene(cfg: Settings, label: str) -> np.ndarray:
    frame = np.zeros((cfg.frame_height, cfg.frame_width, 3), dtype=np.uint8)
    frame[:] = (36, 36, 42)
    # Floor strip
    cv2.rectangle(frame, (0, int(cfg.frame_height * 0.72)), (cfg.frame_width, cfg.frame_height), (48, 48, 54), -1)

    for name, rect, color in [
        ("SOURCE", cfg.source_zone, (70, 120, 70)),
        ("DEST", cfg.destination_zone, (70, 70, 160)),
    ]:
        x, y, w, h = fraction_to_pixels(rect, cfg.frame_width, cfg.frame_height)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, -1)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (220, 220, 220), 2)
        cv2.putText(frame, name, (x + 8, y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1, cv2.LINE_AA)

    cv2.putText(frame, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (230, 230, 120), 2, cv2.LINE_AA)
    return frame


def _draw_object(frame: np.ndarray, cx: float, cy: float, radius: int = 22) -> None:
    # Vivid green BGR — matches HSV lower/upper in settings
    color = (40, 220, 40)
    cv2.circle(frame, (int(cx), int(cy)), radius, color, -1)
    cv2.circle(frame, (int(cx), int(cy)), radius, (20, 80, 20), 2)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _write_frames(path: Path, frames: List[np.ndarray], fps: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open VideoWriter for {path}")
    for frame in frames:
        writer.write(frame)
    writer.release()


def generate_successful(path: Path, cfg: Settings = settings, n_frames: int = 60) -> Path:
    """Object starts in source, travels visibly, settles in destination."""
    source_c, dest_c = _zone_centers(cfg)
    frames: List[np.ndarray] = []
    dwell = 10
    settle = 14
    move = n_frames - dwell - settle
    for i in range(n_frames):
        frame = _draw_scene(cfg, "scenario: successful")
        if i < dwell:
            cx, cy = source_c
        elif i < dwell + move:
            t = (i - dwell) / max(move - 1, 1)
            cx = _lerp(source_c[0], dest_c[0], t)
            cy = _lerp(source_c[1], dest_c[1], t)
        else:
            cx, cy = dest_c
        _draw_object(frame, cx, cy)
        frames.append(frame)
    _write_frames(path, frames, cfg.fps)
    return path


def generate_incomplete(path: Path, cfg: Settings = settings, n_frames: int = 55) -> Path:
    """Object leaves source but stops in transit before destination."""
    source_c, dest_c = _zone_centers(cfg)
    mid = ((_lerp(source_c[0], dest_c[0], 0.45)), (_lerp(source_c[1], dest_c[1], 0.45)))
    frames: List[np.ndarray] = []
    dwell = 10
    move = 20
    for i in range(n_frames):
        frame = _draw_scene(cfg, "scenario: incomplete")
        if i < dwell:
            cx, cy = source_c
        elif i < dwell + move:
            t = (i - dwell) / max(move - 1, 1)
            cx = _lerp(source_c[0], mid[0], t)
            cy = _lerp(source_c[1], mid[1], t)
        else:
            cx, cy = mid
        _draw_object(frame, cx, cy)
        frames.append(frame)
    _write_frames(path, frames, cfg.fps)
    return path


def generate_occluded(path: Path, cfg: Settings = settings, n_frames: int = 70) -> Path:
    """Object disappears long enough that evidence becomes unreliable."""
    source_c, dest_c = _zone_centers(cfg)
    frames: List[np.ndarray] = []
    dwell = 8
    visible_move = 8
    occluded = max(cfg.max_occlusion_gap_frames + 8, 20)
    for i in range(n_frames):
        frame = _draw_scene(cfg, "scenario: occluded")
        if i < dwell:
            _draw_object(frame, source_c[0], source_c[1])
        elif i < dwell + visible_move:
            t = (i - dwell) / max(visible_move - 1, 1)
            cx = _lerp(source_c[0], _lerp(source_c[0], dest_c[0], 0.35), t)
            cy = _lerp(source_c[1], source_c[1], t)
            _draw_object(frame, cx, cy)
        elif i < dwell + visible_move + occluded:
            # Intentionally no object — long occlusion.
            pass
        else:
            # Brief late flicker far from a settled destination streak.
            t = (i - dwell - visible_move - occluded) / max(n_frames - dwell - visible_move - occluded, 1)
            cx = _lerp(_lerp(source_c[0], dest_c[0], 0.5), dest_c[0], min(t, 1.0))
            cy = dest_c[1]
            if i % 3 != 0:
                _draw_object(frame, cx, cy)
        frames.append(frame)
    _write_frames(path, frames, cfg.fps)
    return path


GENERATORS = {
    ScenarioName.SUCCESSFUL: generate_successful,
    ScenarioName.INCOMPLETE: generate_incomplete,
    ScenarioName.OCCLUDED: generate_occluded,
}


def generate_scenario(name: ScenarioName, path: Path, cfg: Settings = settings) -> Path:
    return GENERATORS[name](path, cfg)
