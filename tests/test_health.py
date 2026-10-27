def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "opencv" in data
    assert data["opencv"]


def test_config(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "successful" in data["scenarios"]
    assert data["aws_s3_enabled"] is False
    assert "quality_formula" in data
