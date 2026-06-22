import re
from typing import List

from app.pipeline.base import Detection

_DIGIT_SEQ_RE = re.compile(r"\b(?:\d{4}[-\s]){3}\d{4}\b|\b(?:4\d{15}|5[1-5]\d{14}|3[47]\d{13}|6(?:011|5\d{2})\d{12})\b")


def _luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def detect(text: str) -> List[Detection]:
    detections: List[Detection] = []
    for m in _DIGIT_SEQ_RE.finditer(text):
        if _luhn_valid(m.group()):
            detections.append(Detection(
                start=m.start(), end=m.end(),
                type="credit_card", subtype="luhn_validated", confidence="high",
            ))
    return detections
