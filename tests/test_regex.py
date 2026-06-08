from app.pipeline import regex_stage


def _types(text):
    return [d.type for d in regex_stage.detect(text)]


def test_openai_key():
    assert _types("use this key sk-abcdefghijklmnopqrstuvwxyz123456 to call") != []


def test_email():
    assert "email" in _types("contact me at john.doe@example.com please")


def test_ssn():
    assert "ssn" in _types("my ssn is 123-45-6789")


def test_password_kv():
    hits = _types("password=mysecretpass123")
    assert hits != []


def test_clean_message():
    assert _types("hey can you help me order a pizza?") == []
