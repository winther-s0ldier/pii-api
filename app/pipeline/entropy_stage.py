import math
import re
from typing import List

from app.pipeline.base import Detection

_MIN_LENGTH = 20
_ENTROPY_THRESHOLD = 4.0
_TOKEN_RE = re.compile(r"\S+")


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def detect(text: str) -> List[Detection]:
    detections: List[Detection] = []
    for m in _TOKEN_RE.finditer(text):
        token = m.group()
        # Strip common surrounding punctuation that inflates entropy
        stripped = token.strip("\"'`(),;:")
        if len(stripped) < _MIN_LENGTH:
            continue
        if '://' in stripped or re.search(r"[a-zA-Z0-9._%+\-]+@[^\s@]+\.[a-zA-Z]{2,}", stripped):
            continue
        if _shannon_entropy(stripped) >= _ENTROPY_THRESHOLD:
            detections.append(Detection(
                start=m.start(), end=m.end(),
                type="private_key", subtype="entropy", confidence="high",
            ))
    return detections
