"""Run the three synthetic scenarios end-to-end and print decisions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.models import ScenarioName
from app.services.episode import EpisodeService


def main() -> int:
    service = EpisodeService(settings)
    print("WorldTrace AI demo")
    print(f"Episodes dir: {settings.episodes_dir}")
    results = {}
    for name in ScenarioName:
        detail = service.run_scenario(name.value)
        results[name.value] = {
            "episode_id": detail.episode_id,
            "decision": detail.decision,
            "reason_code": detail.reason_code,
            "quality_score": detail.quality_score,
            "review_status": detail.review_status,
        }
        print(
            f"[{name.value}] {detail.decision} / {detail.reason_code} "
            f"quality={detail.quality_score}"
        )
        if detail.decision == "REVIEW_REQUIRED":
            reviewed = service.review_episode(
                detail.episode_id,
                __import__("app.core.models", fromlist=["ReviewRequest"]).ReviewRequest(
                    action="approve", reviewer="demo-script", notes="demo approval"
                ),
            )
            results[name.value]["review_status"] = reviewed.review_status
            zip_path = service.download_zip(detail.episode_id)
            results[name.value]["zip"] = str(zip_path)
            print(f"  approved + exported {zip_path.name}")
    out = ROOT / "release" / "demo_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
