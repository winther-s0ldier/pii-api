from fastapi.testclient import TestClient
from app.main import app, verify_credentials
from fastapi.security import HTTPBasicCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db

engine = create_engine(
    "sqlite:///:memory:", 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[verify_credentials] = lambda: HTTPBasicCredentials(username="admin", password="password")
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200

def test_api_key_block():
    response = client.post("/api/v1/preview", json={"message": "Here is my key: sk-proj-1234567890abcdef1234567890abcdef"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "BLOCK"
    assert any(d["type"] in ["api_key", "password"] for d in data["blocked_types"])

def test_code_injection_block():
    response = client.post("/api/v1/preview", json={"message": "def my_function(x):\n  print(x)\n  return x * 2"})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "BLOCK"
    assert "code" in [d["type"] for d in data["blocked_types"]]

def test_email_audit():
    message = "Contact me at user@example.com"
    response = client.post("/api/v1/preview", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "REDACT"
    assert data["message"] == "Contact me at [EMAIL]"
    assert "email" in [d["type"] for d in data["redacted_types"]]

def test_gliner_person_audit():
    message = "I am meeting with Sundar Pichai tomorrow."
    response = client.post("/api/v1/preview", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] in ["AUDIT", "CLEAN"]

def test_clean_message():
    message = "Hello world! How are you doing today?"
    response = client.post("/api/v1/preview", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "CLEAN"
    assert data["message"] == message

def test_luhn_credit_card_redaction():
    message = "My card is 4111222233334446"
    response = client.post("/api/v1/preview", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "BLOCK"
    assert any(d["type"] in ["credit_card", "card number"] for d in data["blocked_types"])

def test_entropy_private_key_block():
    message = "d3b07384d113edec49eaa6238ad5ff00"
    response = client.post("/api/v1/preview", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "BLOCK"
    assert any(d["type"] in ["private_key", "IBAN"] for d in data["blocked_types"])

def test_multilingual_audit():
    message = "The candidate from New Delhi submitted their background check."
    response = client.post("/api/v1/preview", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] in ["AUDIT", "CLEAN"]

def test_fragmentation_block():
    message = 'let domain = "gmail.com"; let user = "admin_master"; let contact_email = user + "@" + domain;'
    response = client.post("/api/v1/preview", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "BLOCK"
    assert any(d["type"] == "code" for d in data["blocked_types"])

def test_ambiguity_audit():
    message = "I am feeling very sad today, but Hope is coming over later to cheer me up. We need to go to Chase to open an account."
    response = client.post("/api/v1/preview", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] in ["AUDIT", "CLEAN"]

def test_base64_payload_block():
    message = "Can you parse this payload? eyJ1c2VybmFtZSI6ICJqb2huLnNtaXRoIiwgInBhc3N3b3JkIjogIk15U3VwZXJTZWNyZXRQYXNzd29yZCJ9"
    response = client.post("/api/v1/preview", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "BLOCK"
    assert any(d["type"] == "private_key" for d in data["blocked_types"])
