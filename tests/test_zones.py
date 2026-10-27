from app.core.config import settings
from app.core.models import ZoneName
from app.vision.zones import classify_point


def test_zone_mapping_source():
    sx, sy, sw, sh = settings.source_zone
    assert classify_point(sx + sw / 2, sy + sh / 2, settings) == ZoneName.SOURCE


def test_zone_mapping_destination():
    dx, dy, dw, dh = settings.destination_zone
    assert classify_point(dx + dw / 2, dy + dh / 2, settings) == ZoneName.DESTINATION


def test_zone_mapping_transit():
    sx, sy, sw, sh = settings.source_zone
    dx, dy, dw, dh = settings.destination_zone
    mx = (sx + sw + dx) / 2
    my = (sy + sh / 2 + dy + dh / 2) / 2
    assert classify_point(mx, my, settings) == ZoneName.TRANSIT


def test_zone_mapping_outside():
    assert classify_point(0.5, 0.05, settings) == ZoneName.OUTSIDE
