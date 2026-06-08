import re
from dataclasses import dataclass
from typing import List

from app.pipeline.base import Detection


@dataclass
class _Pattern:
    name: str
    subtype: str
    regex: re.Pattern
    confidence: str = "high"


_PATTERNS: List[_Pattern] = [
    _Pattern("openai_key",      "openai",      re.compile(r"sk-[a-zA-Z0-9]{32,}")),
    _Pattern("openai_proj_key", "openai",      re.compile(r"sk-(?:proj|svcacct|service)-[A-Za-z0-9_\-]+")),
    _Pattern("groq_key",        "groq",        re.compile(r"gsk_[a-zA-Z0-9]{52}")),
    _Pattern("openrouter_key",  "openrouter",  re.compile(r"sk-or-v1-[a-zA-Z0-9]{64}")),
    _Pattern("anthropic_key",   "anthropic",   re.compile(r"sk-ant-[a-zA-Z0-9\-_]{40,}")),
    _Pattern("github_pat",      "github",      re.compile(r"ghp_[a-zA-Z0-9]{36}")),
    _Pattern("github_oauth",    "github",      re.compile(r"gho_[a-zA-Z0-9]{36}")),
    _Pattern("aws_access_key",  "aws",         re.compile(r"AKIA[0-9A-Z]{16}")),
    _Pattern("aws_secret_key",  "aws",         re.compile(r"(?i)aws.{0,20}secret.{0,20}['\"][0-9a-zA-Z/+]{40}['\"]")),
    _Pattern("huggingface",     "huggingface", re.compile(r"hf_[a-zA-Z0-9]{34,}")),
    _Pattern("stripe_key",      "stripe",      re.compile(r"(sk|pk)_(live|test)_[a-zA-Z0-9]{24,}")),
    _Pattern("slack_token",     "slack",       re.compile(r"xox[baprs]-[0-9a-zA-Z\-]{10,}")),
    _Pattern("google_api_key",  "google",      re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    _Pattern("twilio_key",      "twilio",      re.compile(r"SK[0-9a-fA-F]{32}")),
    _Pattern("ssh_private_key", "ssh",         re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----")),
    _Pattern("ssn",             "ssn",         re.compile(r"\b\d\s*\d\s*\d\s*-\s*\d\s*\d\s*-\s*\d\s*\d\s*\d\s*\d\b"), confidence="high"),
    _Pattern("email",           "email",       re.compile(r"\b[a-zA-Z0-9._%+\-]+@[^\s@]+\.[a-zA-Z]{2,}\b"), confidence="medium"),
    _Pattern("ipv4",            "ipv4",        re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"), confidence="medium"),
    _Pattern("hex_ipv4",        "ipv4",        re.compile(r"\b0x[0-9a-fA-F]{8}\b"), confidence="medium"),
    _Pattern("phone_us",        "phone",       re.compile(r"\b(?:\+?\s*1)?\s*\(?\s*\d\s*\d\s*\d\s*\)?\s*[\-\.]?\s*\d\s*\d\s*\d\s*[\-\.]?\s*\d\s*\d\s*\d\s*\d\b"), confidence="medium"),
    _Pattern("bearer_token",    "bearer",      re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*")),
    _Pattern("password_kv",     "password",    re.compile(r"(?i)(password|passwd|pwd|secret|token|api_?key|apikey|auth_?token|auth|key|access_?code)[\'\"\s]*[:=]+[\s>]*[\'\"]?\S{6,}")),
    _Pattern("aadhar",          "tax ID",      re.compile(r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}\b(?![\s\-]\d)"), confidence="high"),
    _Pattern("fake_cc",         "credit_card", re.compile(r"\b\d[\d\s\-]{11,17}\d\b"), confidence="high"),
    _Pattern("spelled_numbers", "ssn",         re.compile(r"(?:(?:zero|one|two|three|four|five|six|seven|eight|nine)[\s\-,]*){9,}"), confidence="high"),
]


def detect(text: str) -> List[Detection]:
    detections: List[Detection] = []
    for p in _PATTERNS:
        for m in p.regex.finditer(text):
            det_type = "api_key" if "key" in p.name or p.name in ("bearer_token", "ssh_private_key") else p.name
            if "ipv4" in p.name:
                det_type = "IP address"
            elif p.name == "password_kv":
                det_type = "password"
            elif p.name == "phone_us":
                det_type = "phone number"
            elif p.name == "spelled_numbers":
                det_type = "ssn"
            elif p.name == "fake_cc":
                det_type = "credit_card"
            elif p.name == "aadhar":
                det_type = "tax ID"
            
            detections.append(Detection(
                start=m.start(),
                end=m.end(),
                type=det_type,
                subtype=p.subtype,
                confidence=p.confidence,
            ))
    return detections
