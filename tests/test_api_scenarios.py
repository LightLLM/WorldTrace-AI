from app.core.models import DecisionAction, ReasonCode


def test_scenario_successful(client):
    res = client.post("/api/scenarios/successful")
    assert res.status_code == 200
    data = res.json()
    assert data["decision"] == DecisionAction.REVIEW_REQUIRED.value
    assert data["reason_code"] == ReasonCode.TRANSFER_EVIDENCE_COMPLETE.value
    assert data["review_status"] == "PENDING"


def test_scenario_incomplete(client):
    res = client.post("/api/scenarios/incomplete")
    assert res.status_code == 200
    data = res.json()
    assert data["decision"] == DecisionAction.RETAKE_REQUIRED.value


def test_scenario_occluded(client):
    res = client.post("/api/scenarios/occluded")
    assert res.status_code == 200
    data = res.json()
    assert data["decision"] == DecisionAction.RETAKE_REQUIRED.value


def test_list_episodes(client):
    client.post("/api/scenarios/successful")
    res = client.get("/api/episodes")
    assert res.status_code == 200
    assert len(res.json()) >= 1
