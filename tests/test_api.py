from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200

def test_api_key_block():
    response = client.post("/api/v1/check", json={"message": "Here is my key: sk-proj-1234567890abcdef1234567890abcdef"})
    assert response.status_code == 400
    assert response.json()["detail"]["action"] == "BLOCK"
    assert "api_key" in [d["type"] for d in response.json()["detail"]["blocked_types"]]

def test_code_injection_block():
    response = client.post("/api/v1/check", json={"message": "def my_function(x):\n  print(x)\n  return x * 2"})
    assert response.status_code == 400
    assert response.json()["detail"]["action"] == "BLOCK"
    assert "code" in [d["type"] for d in response.json()["detail"]["blocked_types"]]

def test_email_audit():
    message = "Contact me at user@example.com"
    response = client.post("/api/v1/check", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "AUDIT"
    assert data["message"] == message
    assert "email" in [d["type"] for d in data["redacted_types"]]

def test_gliner_person_audit():
    message = "I am meeting with Sundar Pichai tomorrow."
    response = client.post("/api/v1/check", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "AUDIT"
    assert "person" in [d["type"] for d in data["redacted_types"]]

def test_clean_message():
    message = "Hello world! How are you doing today?"
    response = client.post("/api/v1/check", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "CLEAN"
    assert data["message"] == message

def test_luhn_credit_card_redaction():
    message = "My card is 4111222233334446"
    response = client.post("/api/v1/check", json={"message": message})
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["action"] == "BLOCK"
    assert any(d["type"] in ["credit_card", "card number"] for d in data["detail"]["blocked_types"])

def test_entropy_private_key_block():
    message = "d3b07384d113edec49eaa6238ad5ff00"
    response = client.post("/api/v1/check", json={"message": message})
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["action"] == "BLOCK"
    assert any(d["type"] in ["private_key", "IBAN"] for d in data["detail"]["blocked_types"])

def test_multilingual_audit():
    message = "The candidate from New Delhi submitted their background check. The Aadhar number they provided is 9876 5432 1098."
    response = client.post("/api/v1/check", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "AUDIT"
    assert any(d["type"] == "location" for d in data["redacted_types"])

def test_fragmentation_block():
    message = 'let domain = "gmail.com"; let user = "admin_master"; let contact_email = user + "@" + domain;'
    response = client.post("/api/v1/check", json={"message": message})
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["action"] == "BLOCK"
    assert any(d["type"] == "code" for d in data["detail"]["blocked_types"])

def test_ambiguity_audit():
    message = "I am feeling very sad today, but Hope is coming over later to cheer me up. We need to go to Chase to open an account."
    response = client.post("/api/v1/check", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "AUDIT"
    assert any(d["type"] == "organization" for d in data["redacted_types"])

def test_base64_payload_block():
    message = "Can you parse this payload? eyJ1c2VybmFtZSI6ICJqb2huLnNtaXRoIiwgInBhc3N3b3JkIjogIk15U3VwZXJTZWNyZXRQYXNzd29yZCJ9"
    response = client.post("/api/v1/check", json={"message": message})
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["action"] == "BLOCK"
    assert any(d["type"] == "private_key" for d in data["detail"]["blocked_types"])
