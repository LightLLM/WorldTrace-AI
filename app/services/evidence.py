"""Evidence-bundle writers: CSV, JSON, manifest, README, ZIP."""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.models import DecisionResult, Observation, ReviewResult, utc_now_iso


def write_observations_csv(path: Path, observations: List[Observation]) -> None:
    fields = [
        "frame_index",
        "timestamp_sec",
        "visible",
        "cx",
        "cy",
        "nx",
        "ny",
        "area",
        "confidence",
        "zone",
        "bbox_x",
        "bbox_y",
        "bbox_w",
        "bbox_h",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for obs in observations:
            bbox = obs.bbox or [None, None, None, None]
            writer.writerow(
                {
                    "frame_index": obs.frame_index,
                    "timestamp_sec": obs.timestamp_sec,
                    "visible": int(obs.visible),
                    "cx": obs.cx,
                    "cy": obs.cy,
                    "nx": obs.nx,
                    "ny": obs.ny,
                    "area": obs.area,
                    "confidence": obs.confidence,
                    "zone": obs.zone.value,
                    "bbox_x": bbox[0],
                    "bbox_y": bbox[1],
                    "bbox_w": bbox[2],
                    "bbox_h": bbox[3],
                }
            )


def write_json(path: Path, payload: Any) -> None:
    if hasattr(payload, "model_dump"):
        data = payload.model_dump(mode="json")
    else:
        data = payload
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_bundle_readme(path: Path, episode_id: str) -> None:
    path.write_text(
        "\n".join(
            [
                "WorldTrace AI Evidence Bundle",
                "=============================",
                f"Episode: {episode_id}",
                "",
                "Contents:",
                "- original.mp4          Raw capture / synthetic input",
                "- annotated.mp4         OpenCV-annotated visualization",
                "- observations.csv      Frame-level tracking observations",
                "- events.json           Zone transitions and occlusion events",
                "- decision.json         Decision action, reason, quality, check trace",
                "- review.json           Human review result (if completed)",
                "- manifest.json         Bundle inventory and hashes placeholder",
                "- README.txt            This file",
                "",
                "This is a research prototype evidence package. It is not a",
                "production warehouse audit certificate.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_manifest(
    path: Path,
    episode_id: str,
    files: List[str],
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "episode_id": episode_id,
        "created_at": utc_now_iso(),
        "files": files,
        "schema_version": "1.0",
        "notes": "Local filesystem evidence bundle. AWS S3 archival is optional and unverified unless configured.",
    }
    if extra:
        payload.update(extra)
    write_json(path, payload)


def build_zip(episode_dir: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(episode_dir.iterdir()):
            if item.is_file() and item.name != zip_path.name:
                zf.write(item, arcname=item.name)
    return zip_path


def save_review(path: Path, review: ReviewResult) -> None:
    write_json(path, review)
