import math
import re
from typing import List

from app.pipeline.base import Detection

from app.config import ENTROPY_THRESHOLD_HEX, ENTROPY_THRESHOLD_BASE64, ENTROPY_THRESHOLD_OTHER
_MIN_LENGTH = 20
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
        stripped = token.strip("\"'`(),;:")
        if len(stripped) < _MIN_LENGTH:
            continue
        if '://' in stripped or re.search(r"[a-zA-Z0-9._%+\-]+@[^\s@]+\.[a-zA-Z]{2,}", stripped):
            continue
        entropy = _shannon_entropy(stripped)
        is_hex = all(c in '0123456789abcdefABCDEF' for c in stripped)
        threshold = ENTROPY_THRESHOLD_HEX if is_hex else ENTROPY_THRESHOLD_BASE64
        
        if entropy >= threshold:
            detections.append(Detection(
                start=m.start(), end=m.end(),
                type="secret", subtype="entropy", confidence="high",
            ))
    return detections
