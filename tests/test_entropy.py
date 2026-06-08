from app.pipeline import entropy_stage


def test_high_entropy_secret():
    secret = "aB3kQmZ9xPwLnVrTyUoIeHgFdSaJcMbN"
    hits = entropy_stage.detect(f"here is my token {secret}")
    assert any(d.type == "private_key" for d in hits)


def test_normal_text_not_flagged():
    hits = entropy_stage.detect("hello how are you doing today")
    assert hits == []
