import csv
import io
import json
import zipfile

from app.core.models import DecisionAction


def test_approval_and_rejection(client):
    ok = client.post("/api/scenarios/successful").json()
    episode_id = ok["episode_id"]

    approved = client.post(
        f"/api/episodes/{episode_id}/review",
        json={"action": "approve", "reviewer": "tester", "notes": "looks good"},
    )
    assert approved.status_code == 200
    assert approved.json()["review_status"] == "APPROVED"
    assert approved.json()["review"]["status"] == "APPROVED"

    # Create another successful episode for reject path
    ok2 = client.post("/api/scenarios/successful").json()
    rejected = client.post(
        f"/api/episodes/{ok2['episode_id']}/review",
        json={"action": "reject", "reviewer": "tester", "notes": "not usable"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["review_status"] == "REJECTED"


def test_approval_guardrail_blocks_retake(client):
    bad = client.post("/api/scenarios/incomplete").json()
    assert bad["decision"] == DecisionAction.RETAKE_REQUIRED.value
    res = client.post(
        f"/api/episodes/{bad['episode_id']}/review",
        json={"action": "approve", "reviewer": "tester"},
    )
    assert res.status_code == 400
    assert "REVIEW_REQUIRED" in res.json()["detail"]


def test_csv_json_and_zip_export(client):
    ep = client.post("/api/scenarios/successful").json()
    episode_id = ep["episode_id"]
    detail = client.get(f"/api/episodes/{episode_id}").json()
    assert detail["decision_payload"]["checks"]
    assert detail["events"] is not None

    z = client.get(f"/api/episodes/{episode_id}/download")
    assert z.status_code == 200
    assert z.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        names = set(zf.namelist())
        assert "original.mp4" in names
        assert "annotated.mp4" in names
        assert "observations.csv" in names
        assert "events.json" in names
        assert "decision.json" in names
        assert "manifest.json" in names
        assert "README.txt" in names
        csv_text = zf.read("observations.csv").decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        assert len(rows) > 0
        decision = json.loads(zf.read("decision.json"))
        assert decision["action"] == DecisionAction.REVIEW_REQUIRED.value


def test_invalid_upload(client):
    res = client.post(
        "/api/episodes/upload",
        files={"file": ("notes.txt", b"not a video", "text/plain")},
    )
    assert res.status_code == 400


def test_home_dashboard(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "WorldTrace AI" in res.text
    assert "Capture Studio" in res.text
