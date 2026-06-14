import re
from typing import List
from app.pipeline.base import Detection
from app.config import CODE_DENSITY_THRESHOLD

_FENCE_PATTERN = re.compile(r'```[a-zA-Z]*\n[\s\S]+?```|~~~[a-zA-Z]*\n[\s\S]+?~~~')

_SIGNATURES = [
    re.compile(r'\b(def \w+\(|class \w+:|from \w+ import \w+|import \w+|os\.system\(|if __name__|print\()'),
    re.compile(r'\b(function \w+\(|const \w+\s*=|let \w+\s*=|var \w+\s*=|require\(|console\.log\()'),
    re.compile(r'\b(SELECT .* FROM|INSERT INTO .* VALUES|UPDATE .* SET|DELETE FROM|DROP TABLE|UNION SELECT|WAITFOR DELAY)', re.IGNORECASE),
    re.compile(r'(#!/w+|sudo |chmod \+x|chown |curl .* -o|wget |bash\s+-c)'),
    re.compile(r'(\$\(.*?\)|eval\s*\(|exec\s*\(|base64\s*-d|Invoke-Expression)', re.IGNORECASE),
    re.compile(r'\b(echo|awk|sed|grep|cut|cat|tr|printf|rev|xxd)\b', re.IGNORECASE)
]

def detect(text: str) -> List[Detection]:
    detections: List[Detection] = []
    
    # 1. Direct Markdown Fences (Always score as Code)
    for m in _FENCE_PATTERN.finditer(text):
        detections.append(Detection(
            start=m.start(), end=m.end(),
            type="code", subtype="markdown_fence", confidence="high"
        ))

    # 2. Heuristic Density Scoring
    keyword_hits = []
    for sig in _SIGNATURES:
        for m in sig.finditer(text):
            keyword_hits.append(Detection(
                start=m.start(), end=m.end(),
                type="code", subtype="heuristic", confidence="medium"
            ))

    if len(keyword_hits) >= CODE_DENSITY_THRESHOLD:
        detections.extend(keyword_hits)

    return detections
