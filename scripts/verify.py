"""Verification helper: print versions and exercise health + scenarios via TestClient."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app


def main() -> int:
    print(f"python={sys.version.split()[0]}")
    print(f"opencv={cv2.__version__}")
    print(f"numpy={np.__version__}")
    client = TestClient(app)
    health = client.get("/api/health").json()
    print("health=", health)
    for name in ("successful", "incomplete", "occluded"):
        ep = client.post(f"/api/scenarios/{name}").json()
        print(f"{name}: decision={ep['decision']} reason={ep['reason_code']} quality={ep['quality_score']}")
    # Guardrail
    bad = client.post("/api/scenarios/incomplete").json()
    blocked = client.post(
        f"/api/episodes/{bad['episode_id']}/review",
        json={"action": "approve"},
    )
    print(f"retake_approval_blocked={blocked.status_code == 400}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
