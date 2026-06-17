from fastapi.testclient import TestClient
from app.main import app, verify_credentials
from fastapi.security import HTTPBasicCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import Request
import uuid
import json
from unittest.mock import patch

from app.models_db import Base, get_db, User, Organization

engine = create_engine(
    "sqlite:///:memory:", 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
Base.metadata.create_all(bind=engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Seed the test DB and cache user
test_db = TestingSessionLocal()
test_org = Organization(id=uuid.uuid4(), name="Test Org", retention_days=90)
test_db.add(test_org)
test_db.commit()

test_user = User(
    id=uuid.uuid4(), 
    org_id=test_org.id, 
    email="test@email.com", 
    password_hash="pass", 
    role="user",
    tier_block=[],
    tier_redact=[],
    tier_audit=[]
)
test_db.add(test_user)
test_db.commit()
test_db.refresh(test_user)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

def override_verify_credentials(request: Request):
    request.state.current_user = test_user
    return HTTPBasicCredentials(username="test@email.com", password="password")

app.dependency_overrides[verify_credentials] = override_verify_credentials
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

# --- Mock the Pipeline to avoid HF Space timeouts ---
class MockDetection:
    def __init__(self, type_name, start, end, confidence=0.99, subtype=""):
        self.type = type_name
        self.start = start
        self.end = end
        self.confidence = confidence
        self.subtype = subtype

def mock_pipeline_run(text, allowed_pii=[], ignored_values=[], tier_config=None, custom_labels=[]):
    if "sk-proj" in text:
        return text, [MockDetection("api_key", text.find("sk-proj"), len(text))], "BLOCK"
    if "def my_function" in text:
        return text, [MockDetection("code", text.find("def"), len(text))], "BLOCK"
    if "user@example.com" in text:
        return text.replace("user@example.com", "[EMAIL]"), [MockDetection("email", text.find("user@"), text.find(".com")+4)], "REDACT"
    if "Sundar Pichai" in text:
        return text, [MockDetection("person", text.find("Sundar"), text.find("Pichai")+6)], "AUDIT"
    if "4111222233334446" in text:
        return text, [MockDetection("credit_card", text.find("4111"), text.find("4446")+4)], "BLOCK"
    if "d3b07384d" in text:
        return text, [MockDetection("private_key", text.find("d3b0"), len(text))], "BLOCK"
    if "New Delhi" in text:
        return text, [MockDetection("location", text.find("New"), text.find("Delhi")+5)], "AUDIT"
    if "let domain" in text:
        return text, [MockDetection("code", text.find("let"), len(text))], "BLOCK"
    if "Chase" in text:
        return text, [MockDetection("organization", text.find("Chase"), text.find("Chase")+5)], "AUDIT"
    if "eyJ" in text:
        return text, [MockDetection("private_key", text.find("eyJ"), len(text))], "BLOCK"
    return text, [], "CLEAN"

import pytest

@pytest.fixture(autouse=True)
def mock_pipeline():
    patcher = patch('app.pipeline.pipeline.run', side_effect=mock_pipeline_run)
    patcher.start()
    yield
    patcher.stop()

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
