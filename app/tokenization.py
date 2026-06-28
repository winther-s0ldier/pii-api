"""
Server-side reversible tokenisation for documents.

The browser handles tokenisation for typed messages (it has the original text),
but for uploaded files the original extracted text only exists here transiently.
So for documents we build value-specific tokens server-side and hand the vault
back to the browser, which holds it (browser-only vault) and restores values in
the model's reply on the client. We never persist the vault.
"""
import re
import hashlib


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:6]


def _token_for(type_: str, value: str) -> str:
    t = re.sub(r"[^A-Z0-9]+", "_", type_.upper()).strip("_")
    return f"[{t}_{_short_hash(value)}]"


def build_tokens(original: str, detections, block_set) -> tuple[str, dict]:
    """
    Replace every non-block detection span in `original` with a deterministic
    token. Returns (tokenised_text, vault) where vault maps token -> real value.
    Block-tier detections are not tokenised (those messages are blocked outright).
    """
    vault: dict = {}
    spans = sorted(
        (d for d in detections if d.type not in block_set),
        key=lambda d: d.start,
        reverse=True,  # replace right-to-left so earlier offsets stay valid
    )
    result = original
    for d in spans:
        value = original[d.start:d.end]
        if not value:
            continue
        token = _token_for(d.type, value)
        result = result[: d.start] + token + result[d.end:]
        vault[token] = value
    return result, vault
