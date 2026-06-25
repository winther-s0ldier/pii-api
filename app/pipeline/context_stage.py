"""
Contextual PII scoring — reduces false positives by examining what surrounds each detection.

Three checks in order:
  1. Structural risk   — key=value / JSON patterns before the span → keep (high confidence)
  2. Educational/safe  — discussion markers around the span → drop (likely benign)
  3. Type-safe rules   — per-type patterns that indicate benign usage → drop
"""
import re
from app.pipeline.base import Detection

WINDOW = 70  # characters on each side to examine

# ── Structural patterns that appear BEFORE the matched span ────────────────────
# If the text before the detection looks like "password: " or `"key": "`, it's
# almost certainly a real credential, not a discussion about one.
_STRUCTURAL_RISK = [
    r'(?:password|passwd|pwd)\s*[:=]\s*\Z',
    r'(?:api[_\-\s]?key|apikey|x-api-key|token|bearer|secret|access_token|auth)\s*[:=]\s*\Z',
    r'(?:email|e-mail|mailto)\s*[:=]\s*\Z',
    r'(?:ssn|social.?security.?number?)\s*[:=]\s*\Z',
    r'(?:card|cc|cvv|cvc|expiry|expiration)\s*[:=]\s*\Z',
    r'(?:phone|mobile|cell|fax|tel)\s*[:=]\s*\Z',
    r'(?:address|addr)\s*[:=]\s*\Z',
    r'"(?:password|key|token|secret|email|ssn|card|phone|address)"\s*:\s*"?\Z',
    r"'(?:password|key|token|secret|email|ssn|card|phone|address)'\s*:\s*'?\Z",
    r'(?:my|your|his|her|our|their)\s+\w+\s+is\s*\Z',
    r'(?:here is|here\'s|this is)\s+(?:my|your|the|an?)\s+\Z',
    r'(?:send|email|contact|reach)\s+(?:me|us|him|her|them)\s+at\s*\Z',
    r'(?:login|log in|sign in)\s+(?:with|using)\s*\Z',
    r'Authorization:\s*Bearer\s*\Z',
    r'--header\s+\Z', r'-H\s+["\']?\Z',   # curl -H patterns
]

# ── Universal educational/safe markers ────────────────────────────────────────
# Two or more of these near a detection → likely discussing the concept, not sharing it
_EDUCATIONAL_MARKERS = [
    "example", "sample", "e.g.", "eg.", "i.e.", "such as", "for instance",
    "placeholder", "dummy", "fake", "test", "demo", "template",
    "tutorial", "documentation", "docs", "guide", "how to", "best practice",
    "never share", "don't share", "do not share", "avoid sending",
    "protect your", "secure your", "safeguard",
    "reset your", "change your", "forgot your", "recover your",
    "policy", "requirement", "must be", "should be", "needs to be",
    "[redacted]", "xxx", "****", "•••", "########",
    "format is", "looks like", "format:", "structure:", "example:",
    "not a real", "not an actual", "fictional", "hypothetical",
]

# ── Per-type benign patterns ───────────────────────────────────────────────────
# If any of these match in the surrounding context, the detection is likely a
# false positive — discussing the concept rather than sharing actual PII.
_TYPE_BENIGN: dict[str, list[str]] = {
    "password": [
        r'\bpassword\s+(?:policy|requirement|strength|length|manager|hint|tip|complexity|rule)',
        r'\b(?:strong|weak|good|bad|secure|insecure|complex|simple)\s+password\b',
        r'\bpassword\s+(?:must|should|needs?|has? to|cannot|can\'t)\b',
        r'\b(?:reset|forgot|change|update|recover|lost)\s+(?:your\s+)?password\b(?!\s*[:=])',
        r'\bpassword\s+(?:length|expir|rotation|history|reuse)',
        r'\bhow\s+to\s+(?:create|set|choose|pick|make)\s+(?:a\s+)?(?:strong\s+)?password\b',
    ],
    "api_key": [
        r'\bapi\s*key\s+(?:format|example|structure|documentation|pattern)',
        r'\bgenerate\s+(?:an?\s+)?api\s*key\b(?!\s*:\s*[A-Za-z0-9])',
        r'\bapi\s*key\s+(?:starts?|begins?|looks?|ends?|contains?|consists?)',
        r'\bwhat\s+(?:is|does)\s+(?:an?\s+)?api\s*key\b',
        r'\bapi\s*key\s+(?:authentication|based|management)',
    ],
    "email": [
        r'\b@example\.com\b',
        r'\bexample@\b', r'\btest@\b', r'\buser@domain\b', r'\bname@\b',
        r'\bemail\s+(?:address\s+)?(?:format|field|placeholder|validation|pattern)',
        r'\benter\s+(?:your\s+)?email\b',
        r'\bvalid\s+email\b', r'\binvalid\s+email\b',
    ],
    "credit_card": [
        r'\btest\s+card\b', r'\bsample\s+card\b', r'\bdemo\s+card\b',
        r'\b4111[ -]?1111\b', r'\b4242[ -]?4242\b', r'\b5555[ -]?5555\b',
        r'\bcredit\s+card\s+(?:number\s+)?(?:format|example|validation|pattern)',
        r'\b16.digit\b', r'\bcard\s+number\s+format\b',
    ],
    "ssn": [
        r'\bssn\s+format\b', r'\bsocial\s+security\s+(?:format|example|field|pattern)',
        r'\b123.?45.?6789\b', r'\b000.?00.?0000\b', r'\b999.?99.?9999\b',
        r'\bformat\s+is\s+\d{3}.?\d{2}.?\d{4}\b',
    ],
    "phone number": [
        r'\b1-?800\b', r'\b555-?\d{4}\b',
        r'\b(?:call|text|fax)\s+(?:us|me|them)\s+at\b',
        r'\bphone\s+(?:number\s+)?(?:format|example|pattern|field)',
        r'\bcontact\s+number\b',
    ],
    "location": [
        r'\b(?:weather|forecast|temperature|sunny|raining|cloudy|windy)\b',
        r'\b(?:i am from|i\'m from|born in|grew up in|based in|originally from)\b',
        r'\b(?:visiting|traveling|travelling|heading to|going to|moving to)\b',
        r'\b(?:map|directions?|navigate|route|gps)\b',
        r'\blocated\s+(?:in|at|near)\b',
    ],
    "person": [
        r'\b(?:hi|hello|hey|howdy|dear|greetings|good\s+(?:morning|afternoon|evening))\b',
        r'\b(?:the\s+)?(?:author|user|person|customer|client|employee|patient)\b',
        r'\bexample\s+(?:name|person|user)\b',
        r'\bjohn\s+doe\b', r'\bjane\s+doe\b',  # Common placeholder names
    ],
    "organization": [
        r'\b(?:the|a|your|our)\s+company\b',
        r'\bexample\s+(?:corp|inc|company|organization|org)\b',
        r'\bacme\b',  # Classic placeholder org
        r'\bfoo\s*(?:bar|corp|inc)?\b',
    ],
    "IP address": [
        r'\b192\.168\.\b', r'\b127\.0\.0\.1\b', r'\b0\.0\.0\.0\b',
        r'\b(?:localhost|loopback|local\s+ip)\b',
        r'\bip\s+address\s+(?:format|example|range|scheme)\b',
        r'\bsubnet\b', r'\bcidr\b',
    ],
    "code": [
        r'\bcode\s+(?:snippet|sample|example|block|review)\b',
        r'\b(?:for\s+example|here\'s\s+(?:an?\s+)?example|sample\s+code)\b',
    ],
}

# ── Per-type risky patterns ────────────────────────────────────────────────────
# These in the context around a detection increase confidence it's real PII.
_TYPE_RISKY: dict[str, list[str]] = {
    "password": [
        r'\b(?:my|the|your|his|her|our)\s+password\s+is\b',
        r'\bpassword\s*[:=]\s*\S',
        r'\bcredentials?\b',
        r'\blogged\s+in\s+(?:with|using)\b',
    ],
    "api_key": [
        r'\bapi[_\-\s]?key\s*[:=]\s*[A-Za-z0-9_\-]{16,}',
        r'\bAuthorization\s*:\s*Bearer\b',
        r'\btoken\s*[:=]\s*\S{16,}',
        r'\bsecret\s*[:=]\s*\S',
    ],
    "email": [
        r'\b(?:my|his|her|their|our)\s+email\s+(?:address\s+)?is\b',
        r'\bcontact\s+(?:me|him|her|them|us)\s+at\b',
        r'\bsend\s+(?:an?\s+)?(?:email\s+)?to\b',
        r'\breply\s+to\b',
    ],
    "credit_card": [
        r'\bcharge\s+(?:my|the|this)\s+card\b',
        r'\bcard\s+(?:number|no|#)\s*[:=]?\s*\d',
        r'\bcvv\s*[:=]\s*\d',
    ],
}


def _get_context(text: str, start: int, end: int) -> tuple[str, str]:
    left = text[max(0, start - WINDOW):start].lower()
    right = text[end:min(len(text), end + WINDOW)].lower()
    return left, right


def should_keep(text: str, detection: Detection) -> bool:
    """
    Returns True  → detection is likely real PII, keep it.
    Returns False → context suggests benign/educational usage, discard.
    """
    start, end = detection.start, detection.end
    det_type = detection.type.lower().replace("_", " ")
    left_ctx, right_ctx = _get_context(text, start, end)
    span = text[start:end].lower()
    full_ctx = left_ctx + " " + span + " " + right_ctx

    # ── 1. Structural risk: strong signal of actual credential sharing ──────
    for pat in _STRUCTURAL_RISK:
        if re.search(pat, left_ctx, re.I):
            return True

    # ── 2. Type-specific risky patterns ────────────────────────────────────
    for type_key, patterns in _TYPE_RISKY.items():
        nkey = type_key.lower().replace("_", " ")
        if nkey in det_type or det_type in nkey:
            if any(re.search(p, full_ctx, re.I) for p in patterns):
                return True

    # ── 3. Educational/discussion markers ──────────────────────────────────
    # Two or more generic safe markers → likely discussing the concept.
    # Word-boundary match so "test" doesn't fire on "latest" / "demo" on
    # "demographic" — a false hit here would DROP real PII (a privacy leak).
    educational_hits = sum(
        1 for m in _EDUCATIONAL_MARKERS
        if re.search(r'(?<!\w)' + re.escape(m) + r'(?!\w)', full_ctx)
    )
    if educational_hits >= 2:
        return False

    # ── 4. Type-specific benign patterns ───────────────────────────────────
    for type_key, patterns in _TYPE_BENIGN.items():
        nkey = type_key.lower().replace("_", " ")
        if nkey in det_type or det_type in nkey:
            if any(re.search(p, full_ctx, re.I) for p in patterns):
                return False

    return True
