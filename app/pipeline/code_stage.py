import re
from typing import List
from app.pipeline.base import Detection
from app.config import CODE_DENSITY_THRESHOLD

_FENCE_PATTERN = re.compile(r'```[a-zA-Z]*\n[\s\S]+?```|~~~[a-zA-Z]*\n[\s\S]+?~~~')

_SIGNATURES = [
    re.compile(r'\b(def \w+\(|class \w+:|from \w+ import \w+|import \w+|os\.system\(|if __name__|print\()'),
    re.compile(r'\b(function \w+\(|const \w+\s*=|let \w+\s*=|var \w+\s*=|require\(|console\.log\()'),
    re.compile(r'\b(SELECT .* FROM|INSERT INTO .* VALUES|UPDATE .* SET|DELETE FROM|DROP TABLE|UNION SELECT|WAITFOR DELAY)', re.IGNORECASE),
    re.compile(r'(#!/(?:usr/)?bin/(?:env\s+)?\w+|sudo |chmod \+x|chown |curl .* -o|wget |bash\s+-c)'),
    re.compile(r'(\$\(.*?\)|eval\s*\(|exec\s*\(|base64\s*-d|Invoke-Expression)', re.IGNORECASE),
    # ponytail: these words are also plain English (cat/cut/tr/rev...), so only count them
    # as code when they sit in a real shell context — piped, or followed by a flag/path/$var/quoted arg.
    # Without this guard, "I have a cat and need to cut costs" tripped the code-injection BLOCK.
    re.compile(r'(?:\||;|&&)\s*(?:echo|awk|sed|grep|cut|cat|tr|printf|rev|xxd)\b'
               r'|\b(?:echo|awk|sed|grep|cut|cat|tr|printf|rev|xxd)\s+(?:-{1,2}[a-zA-Z]|/[\w.]|\$|["\'])', re.IGNORECASE)
]

def detect(text: str) -> List[Detection]:
    detections: List[Detection] = []
    
    for m in _FENCE_PATTERN.finditer(text):
        detections.append(Detection(
            start=m.start(), end=m.end(),
            type="code", subtype="markdown_fence", confidence="high"
        ))

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
