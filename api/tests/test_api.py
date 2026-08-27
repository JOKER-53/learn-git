from fastapi.testclient import TestClient
import os
import sys

# We need to set a secure SECRET_KEY for the tests
os.environ["SECRET_KEY"] = "test-secret-key-that-is-secure"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from api.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
