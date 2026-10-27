"""HSV color segmentation, morphology, contour tracking."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.core.config import Settings, settings
from app.core.models import Observation, ZoneName
from app.vision.zones import classify_point, zone_pixel_map


def segment_object(
    frame_bgr: np.ndarray,
    hsv_lower: Tuple[int, int, int],
    hsv_upper: Tuple[int, int, int],
) -> np.ndarray:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    lower = np.array(hsv_lower, dtype=np.uint8)
    upper = np.array(hsv_upper, dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    return mask


def best_contour(
    mask: np.ndarray, min_area: float
) -> Optional[Tuple[np.ndarray, float, Tuple[int, int, int, int], Tuple[float, float]]]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    best = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(best))
    if area < min_area:
        return None
    x, y, w, h = cv2.boundingRect(best)
    m = cv2.moments(best)
    if m["m00"] == 0:
        return None
    cx = float(m["m10"] / m["m00"])
    cy = float(m["m01"] / m["m00"])
    return best, area, (x, y, w, h), (cx, cy)


def observation_confidence(area: float, frame_area: float) -> float:
    """Heuristic confidence in [0, 1] from relative contour area."""
    if frame_area <= 0:
        return 0.0
    ratio = area / frame_area
    # Peak confidence around ~1–4% of frame; clamp.
    return float(max(0.0, min(1.0, ratio / 0.02)))


def process_frame(
    frame_bgr: np.ndarray,
    frame_index: int,
    fps: float,
    cfg: Settings = settings,
) -> Observation:
    h, w = frame_bgr.shape[:2]
    mask = segment_object(frame_bgr, cfg.hsv_lower, cfg.hsv_upper)
    result = best_contour(mask, cfg.min_contour_area)
    ts = frame_index / max(fps, 1e-6)
    if result is None:
        return Observation(
            frame_index=frame_index,
            timestamp_sec=ts,
            visible=False,
            zone=ZoneName.OUTSIDE,
        )
    _contour, area, bbox, (cx, cy) = result
    nx, ny = cx / w, cy / h
    zone = classify_point(nx, ny, cfg)
    return Observation(
        frame_index=frame_index,
        timestamp_sec=round(ts, 4),
        visible=True,
        cx=round(cx, 2),
        cy=round(cy, 2),
        nx=round(nx, 4),
        ny=round(ny, 4),
        area=round(area, 2),
        confidence=round(observation_confidence(area, float(w * h)), 4),
        zone=zone,
        bbox=[int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])],
    )


def annotate_frame(
    frame_bgr: np.ndarray,
    obs: Observation,
    trajectory: List[Tuple[int, int]],
    cfg: Settings = settings,
    state_label: str = "",
) -> np.ndarray:
    out = frame_bgr.copy()
    zones = zone_pixel_map(cfg)
    colors = {
        "source": (80, 180, 80),
        "destination": (80, 80, 220),
        "transit": (180, 180, 80),
    }
    for name, (x, y, w, h) in zones.items():
        cv2.rectangle(out, (x, y), (x + w, y + h), colors[name], 2)
        cv2.putText(
            out,
            name.upper(),
            (x + 4, y + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            colors[name],
            1,
            cv2.LINE_AA,
        )

    if len(trajectory) >= 2:
        pts = np.array(trajectory, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(out, [pts], False, (0, 255, 255), 2, cv2.LINE_AA)

    if obs.visible and obs.bbox and obs.cx is not None and obs.cy is not None:
        x, y, w, h = obs.bbox
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(out, (int(obs.cx), int(obs.cy)), 5, (0, 0, 255), -1)
        cv2.putText(
            out,
            f"{obs.zone.value} conf={obs.confidence:.2f}",
            (x, max(16, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (240, 240, 240),
            1,
            cv2.LINE_AA,
        )

    cv2.putText(
        out,
        f"frame={obs.frame_index}",
        (8, cfg.frame_height - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (230, 230, 230),
        1,
        cv2.LINE_AA,
    )
    if state_label:
        cv2.putText(
            out,
            state_label,
            (8, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 220, 100),
            2,
            cv2.LINE_AA,
        )
    return out


def track_video(
    video_path: Path,
    annotated_path: Path,
    cfg: Settings = settings,
) -> List[Observation]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or cfg.fps
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or cfg.frame_width)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or cfg.frame_height)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(annotated_path), fourcc, fps, (width, height))

    observations: List[Observation] = []
    trajectory: List[Tuple[int, int]] = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        obs = process_frame(frame, idx, fps, cfg)
        observations.append(obs)
        if obs.visible and obs.cx is not None and obs.cy is not None:
            trajectory.append((int(obs.cx), int(obs.cy)))
        state = obs.zone.value if obs.visible else "occluded/missing"
        annotated = annotate_frame(frame, obs, trajectory, cfg, state_label=state)
        writer.write(annotated)
        idx += 1

    cap.release()
    writer.release()
    return observations
