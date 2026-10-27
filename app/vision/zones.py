"""Zone geometry helpers for source / transit / destination classification."""

from __future__ import annotations

from typing import Dict, Tuple

from app.core.config import Settings
from app.core.models import ZoneName


Rect = Tuple[float, float, float, float]


def fraction_to_pixels(rect: Rect, width: int, height: int) -> Tuple[int, int, int, int]:
    x, y, w, h = rect
    return (
        int(x * width),
        int(y * height),
        int(w * width),
        int(h * height),
    )


def point_in_rect(nx: float, ny: float, rect: Rect) -> bool:
    x, y, w, h = rect
    return x <= nx <= x + w and y <= ny <= y + h


def classify_point(nx: float, ny: float, settings: Settings) -> ZoneName:
    if point_in_rect(nx, ny, settings.source_zone):
        return ZoneName.SOURCE
    if point_in_rect(nx, ny, settings.destination_zone):
        return ZoneName.DESTINATION
    # Transit corridor between source right edge and destination left edge
    sx, sy, sw, sh = settings.source_zone
    dx, dy, dw, dh = settings.destination_zone
    transit = (sx + sw, min(sy, dy), dx - (sx + sw), max(sy + sh, dy + dh) - min(sy, dy))
    if point_in_rect(nx, ny, transit):
        return ZoneName.TRANSIT
    return ZoneName.OUTSIDE


def zone_pixel_map(settings: Settings) -> Dict[str, Tuple[int, int, int, int]]:
    w, h = settings.frame_width, settings.frame_height
    sx, sy, sw, sh = settings.source_zone
    dx, dy, dw, dh = settings.destination_zone
    transit = (sx + sw, min(sy, dy), dx - (sx + sw), max(sy + sh, dy + dh) - min(sy, dy))
    return {
        "source": fraction_to_pixels(settings.source_zone, w, h),
        "destination": fraction_to_pixels(settings.destination_zone, w, h),
        "transit": fraction_to_pixels(transit, w, h),
    }
