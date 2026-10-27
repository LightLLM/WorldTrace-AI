"""Episode lifecycle: create, process, review, export."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException, UploadFile

from app.core.config import Settings, settings
from app.core.models import (
    DecisionAction,
    DecisionResult,
    EpisodeDetail,
    EpisodeSummary,
    Observation,
    ReviewRequest,
    ReviewResult,
    ReviewStatus,
    ScenarioName,
    utc_now_iso,
)
from app.services.decision import evaluate_transfer, extract_events
from app.services.evidence import (
    build_zip,
    save_review,
    write_bundle_readme,
    write_json,
    write_manifest,
    write_observations_csv,
)
from app.services.synthetic import generate_scenario
from app.vision.tracker import track_video


class EpisodeService:
    def __init__(self, cfg: Settings = settings):
        self.cfg = cfg
        self.root = cfg.episodes_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, episode_id: str) -> Path:
        return self.root / episode_id

    def _meta_path(self, episode_id: str) -> Path:
        return self._dir(episode_id) / "meta.json"

    def _load_meta(self, episode_id: str) -> Dict:
        path = self._meta_path(episode_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Episode not found: {episode_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_meta(self, episode_id: str, meta: Dict) -> None:
        write_json(self._meta_path(episode_id), meta)

    def create_episode(self, scenario: Optional[str] = None, source: str = "upload") -> str:
        episode_id = f"ep_{utc_now_iso().replace(':', '').replace('-', '')}_{uuid.uuid4().hex[:8]}"
        ep_dir = self._dir(episode_id)
        ep_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "episode_id": episode_id,
            "created_at": utc_now_iso(),
            "scenario": scenario,
            "source": source,
            "status": "created",
            "review_status": ReviewStatus.PENDING.value,
            "tracked_frames": 0,
            "total_frames": 0,
        }
        self._save_meta(episode_id, meta)
        return episode_id

    async def save_upload(self, file: UploadFile) -> str:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Missing filename.")
        suffix = Path(file.filename).suffix.lower()
        if suffix not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{suffix}'. Use mp4/avi/mov/mkv/webm.",
            )
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty upload.")
        if len(content) > 80 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File exceeds 80 MB limit.")

        episode_id = self.create_episode(scenario=None, source="upload")
        dest = self._dir(episode_id) / "original.mp4"
        dest.write_bytes(content)
        meta = self._load_meta(episode_id)
        meta["original_filename"] = file.filename
        meta["status"] = "uploaded"
        self._save_meta(episode_id, meta)
        return episode_id

    def run_scenario(self, scenario_name: str) -> EpisodeDetail:
        try:
            scenario = ScenarioName(scenario_name)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown scenario '{scenario_name}'. "
                f"Use: {[s.value for s in ScenarioName]}",
            ) from exc

        episode_id = self.create_episode(scenario=scenario.value, source="synthetic")
        original = self._dir(episode_id) / "original.mp4"
        generate_scenario(scenario, original, self.cfg)
        return self.process_episode(episode_id)

    def process_episode(self, episode_id: str) -> EpisodeDetail:
        meta = self._load_meta(episode_id)
        ep_dir = self._dir(episode_id)
        original = ep_dir / "original.mp4"
        if not original.exists():
            raise HTTPException(status_code=400, detail="original.mp4 missing; upload or generate first.")

        annotated = ep_dir / "annotated.mp4"
        meta["status"] = "processing"
        self._save_meta(episode_id, meta)

        observations = track_video(original, annotated, self.cfg)
        decision = evaluate_transfer(observations, self.cfg)
        events = extract_events(observations)

        write_observations_csv(ep_dir / "observations.csv", observations)
        write_json(ep_dir / "events.json", events)
        write_json(ep_dir / "decision.json", decision)
        write_bundle_readme(ep_dir / "README.txt", episode_id)

        review_status = (
            ReviewStatus.PENDING
            if decision.action == DecisionAction.REVIEW_REQUIRED
            else ReviewStatus.NOT_ELIGIBLE
        )

        files = [
            "original.mp4",
            "annotated.mp4",
            "observations.csv",
            "events.json",
            "decision.json",
            "README.txt",
            "manifest.json",
        ]
        write_manifest(
            ep_dir / "manifest.json",
            episode_id,
            files,
            extra={
                "decision": decision.action.value,
                "reason_code": decision.reason_code.value,
                "quality_score": decision.quality_score,
                "scenario": meta.get("scenario"),
            },
        )

        meta.update(
            {
                "status": "processed",
                "decision": decision.action.value,
                "reason_code": decision.reason_code.value,
                "quality_score": decision.quality_score,
                "review_status": review_status.value,
                "tracked_frames": sum(1 for o in observations if o.visible),
                "total_frames": len(observations),
                "summary": decision.summary,
            }
        )
        self._save_meta(episode_id, meta)
        write_json(ep_dir / "observations.json", [o.model_dump(mode="json") for o in observations])
        return self.get_episode(episode_id)

    def list_episodes(self) -> List[EpisodeSummary]:
        items: List[EpisodeSummary] = []
        for path in sorted(self.root.glob("ep_*"), reverse=True):
            if not (path / "meta.json").exists():
                continue
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
            items.append(self._summary_from_meta(meta))
        return items

    def get_episode(self, episode_id: str) -> EpisodeDetail:
        meta = self._load_meta(episode_id)
        ep_dir = self._dir(episode_id)
        decision_payload = None
        if (ep_dir / "decision.json").exists():
            decision_payload = DecisionResult.model_validate_json(
                (ep_dir / "decision.json").read_text(encoding="utf-8")
            )
        events = []
        if (ep_dir / "events.json").exists():
            events = json.loads((ep_dir / "events.json").read_text(encoding="utf-8"))
        review = None
        if (ep_dir / "review.json").exists():
            review = ReviewResult.model_validate_json(
                (ep_dir / "review.json").read_text(encoding="utf-8")
            )
        media = {}
        for name in ("original.mp4", "annotated.mp4"):
            if (ep_dir / name).exists():
                media[name] = f"/media/{episode_id}/{name}"
        summary = self._summary_from_meta(meta)
        return EpisodeDetail(
            **summary.model_dump(),
            events=events,
            decision_payload=decision_payload,
            review=review,
            media=media,
        )

    def review_episode(self, episode_id: str, request: ReviewRequest) -> EpisodeDetail:
        meta = self._load_meta(episode_id)
        if meta.get("status") != "processed":
            raise HTTPException(status_code=400, detail="Episode must be processed before review.")
        if meta.get("decision") != DecisionAction.REVIEW_REQUIRED.value:
            raise HTTPException(
                status_code=400,
                detail="Only episodes with REVIEW_REQUIRED may be approved or rejected. "
                "Retake-required episodes are not eligible for approval.",
            )
        action = request.action.strip().lower()
        if action not in {"approve", "reject"}:
            raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'.")

        status = ReviewStatus.APPROVED if action == "approve" else ReviewStatus.REJECTED
        review = ReviewResult(
            status=status,
            reviewer=request.reviewer or "local-reviewer",
            notes=request.notes or "",
            reviewed_at=utc_now_iso(),
        )
        save_review(self._dir(episode_id) / "review.json", review)
        meta["review_status"] = status.value
        self._save_meta(episode_id, meta)

        # Refresh manifest to include review.json
        manifest_path = self._dir(episode_id) / "manifest.json"
        files = [
            "original.mp4",
            "annotated.mp4",
            "observations.csv",
            "events.json",
            "decision.json",
            "review.json",
            "README.txt",
            "manifest.json",
        ]
        write_manifest(
            manifest_path,
            episode_id,
            files,
            extra={
                "decision": meta.get("decision"),
                "reason_code": meta.get("reason_code"),
                "quality_score": meta.get("quality_score"),
                "review_status": status.value,
            },
        )
        return self.get_episode(episode_id)

    def download_zip(self, episode_id: str) -> Path:
        meta = self._load_meta(episode_id)
        if meta.get("status") != "processed":
            raise HTTPException(status_code=400, detail="Process the episode before download.")
        ep_dir = self._dir(episode_id)
        zip_path = ep_dir / f"{episode_id}_evidence.zip"
        return build_zip(ep_dir, zip_path)

    def trajectory_points(self, episode_id: str) -> List[Dict]:
        path = self._dir(episode_id) / "observations.json"
        if not path.exists():
            return []
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [
            {"frame": r["frame_index"], "nx": r["nx"], "ny": r["ny"], "zone": r["zone"]}
            for r in rows
            if r.get("visible") and r.get("nx") is not None
        ]

    @staticmethod
    def _summary_from_meta(meta: Dict) -> EpisodeSummary:
        return EpisodeSummary(
            episode_id=meta["episode_id"],
            created_at=meta.get("created_at", ""),
            scenario=meta.get("scenario"),
            status=meta.get("status", "unknown"),
            decision=meta.get("decision"),
            reason_code=meta.get("reason_code"),
            review_status=ReviewStatus(meta.get("review_status", ReviewStatus.PENDING.value)),
            quality_score=meta.get("quality_score"),
            tracked_frames=meta.get("tracked_frames", 0),
            total_frames=meta.get("total_frames", 0),
        )


episode_service = EpisodeService()
