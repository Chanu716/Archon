from fastapi.testclient import TestClient
from archon.main import app
from archon.config import settings

client = TestClient(app)

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "version": settings.ARCHON_VERSION,
    }
