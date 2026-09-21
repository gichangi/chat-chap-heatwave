import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import app


def test_health_and_service_info():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/api/v1/info")
        assert response.status_code == 200
        assert response.json()["id"] == "heatwave-covariate-model"
