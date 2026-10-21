# test_live_calls.py
import requests
import hmac
import hashlib
import json

API_BASE = "http://localhost:8080"  # Sandbox port
TEST_KEY = "test-key-1"
TEST_SECRET = TEST_KEY  # For sandbox only

def sign_payload(payload: dict) -> str:
    return hmac.new(
        TEST_SECRET.encode(),
        json.dumps(payload).encode(),
        hashlib.sha256
    ).hexdigest()

def test_health():
    response = requests.get(f"{API_BASE}/health")
    assert response.status_code == 200
    assert "healthy" in response.json()["status"]

def test_concept_transform():
    payload = {"description": "A modular API gateway for Twingate"}
    signature = sign_payload(payload)
    headers = {
        "X-API-Key": TEST_KEY,
        "X-Signature": signature
    }
    response = requests.post(
        f"{API_BASE}/v1/concept",
        json=payload,
        headers=headers
    )
    assert response.status_code == 200
    assert "design_id" in response.json()["data"]