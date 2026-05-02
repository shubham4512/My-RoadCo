import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.main import app


client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_routes_search_returns_matches() -> None:
    response = client.post(
        "/routes/search",
        json={"from_stop": "Chandigarh", "to_stop": "Delhi"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "matches" in payload
    assert len(payload["matches"]) >= 1


def test_driver_location_update_requires_api_key() -> None:
    response = client.post("/buses/1/location", json={"lat": 29.9, "lng": 76.9})
    assert response.status_code == 401


def test_driver_location_update_accepts_valid_api_key() -> None:
    response = client.post(
        "/buses/1/location",
        json={"lat": 29.9, "lng": 76.9},
        headers={"X-API-Key": "dev-driver-key"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
