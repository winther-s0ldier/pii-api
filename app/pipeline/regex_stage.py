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
    _Pattern("aws_access_key",  "aws",         re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    _Pattern("jwt_token",       "jwt",         re.compile(r"eyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}"), confidence="high"),
    _Pattern("aws_secret_key",  "aws",         re.compile(r"(?i)aws.{0,20}secret.{0,20}['\"][0-9a-zA-Z/+]{40}['\"]")),
    _Pattern("huggingface",     "huggingface", re.compile(r"hf_[a-zA-Z0-9]{34,}")),
    _Pattern("stripe_key",      "stripe",      re.compile(r"(sk|pk)_(live|test)_[a-zA-Z0-9]{24,}")),
    _Pattern("slack_token",     "slack",       re.compile(r"xox[baprs]-[0-9a-zA-Z\-]{10,}")),
    _Pattern("google_api_key",  "google",      re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    _Pattern("twilio_key",      "twilio",      re.compile(r"SK[0-9a-fA-F]{32}")),
    _Pattern("ssh_private_key", "ssh",         re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----")),
    # ponytail: inter-digit whitespace limited to [ \t] (was \s, which matched newlines and
    # stitched a vertical OCR digit-column into an SSN). Inline-spaced obfuscation is still
    # caught on purpose — that's deliberate evasion of a redactor.
    _Pattern("ssn",             "ssn",         re.compile(r"\b\d[ \t]*\d[ \t]*\d[ \t]*-[ \t]*\d[ \t]*\d[ \t]*-[ \t]*\d[ \t]*\d[ \t]*\d[ \t]*\d\b"), confidence="high"),
    _Pattern("email",           "email",       re.compile(r"\b[a-zA-Z0-9._%+\-]+@[^\s@]+\.[a-zA-Z]{2,}\b"), confidence="medium"),
    _Pattern("ipv4",            "ipv4",        re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"), confidence="medium"),
    _Pattern("hex_ipv4",        "ipv4",        re.compile(r"\b0x[0-9a-fA-F]{8}\b"), confidence="medium"),
    # ponytail: inter-digit whitespace limited to [ \t] (was \s). Newlines no longer stitch a
    # vertical OCR digit-column into a phone number; inline-spaced obfuscation is still caught.
    _Pattern("phone_us",        "phone",       re.compile(r"\b(?:\+?[ \t]*1)?[ \t]*\(?[ \t]*\d[ \t]*\d[ \t]*\d[ \t]*\)?[ \t]*[\-\.]?[ \t]*\d[ \t]*\d[ \t]*\d[ \t]*[\-\.]?[ \t]*\d[ \t]*\d[ \t]*\d[ \t]*\d\b"), confidence="medium"),
    _Pattern("bearer_token",    "bearer",      re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*")),
    _Pattern("password_kv",     "password",    re.compile(r"(?i)(password|passwd|pwd|secret|api_?key|apikey|auth_?token|access_?code)[\'\"\s]*[:=]+[\s>]*[\'\"]?\S{6,}")),
    _Pattern("aadhar",          "tax ID",      re.compile(r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}\b(?![\s\-]\d)"), confidence="high"),
    _Pattern("pan_card",        "tax ID",      re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b"), confidence="high"),
    _Pattern("voter_id",        "tax ID",      re.compile(r"\b[A-Z]{3}[0-9]{7}\b"), confidence="high"),
    _Pattern("upi_id",          "upi",         re.compile(r"\b[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}\b"), confidence="medium"),
    _Pattern("phone_in",        "phone",       re.compile(r"\b(?:\+91[\-\s]?)?[0]?(?:[6-9]\d{9})\b"), confidence="high"),
    # ponytail: grouped form needs separators; bare form must carry a real card prefix
    # (Visa 4 / MC 51-55 / Amex 34,37 / Discover). The old \d{15,16} blocked ANY 15-16 digit
    # run (IMEIs, order/tracking IDs) as a card with no Luhn check — a heavy FP source.
    _Pattern("fake_cc",         "credit_card", re.compile(r"\b(?:\d{4}[-\s]){3}\d{4}\b|\b(?:4\d{15}|5[1-5]\d{14}|3[47]\d{13}|6(?:011|5\d{2})\d{12})\b"), confidence="high"),
    _Pattern("spelled_numbers", "ssn",         re.compile(r"(?:(?:zero|one|two|three|four|five|six|seven|eight|nine)[\s\-,]*){9,}"), confidence="high"),
    _Pattern("spelled_date",    "date_time",   re.compile(r"(?i)\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(?:two|twenty|nineteen)\s+[a-z]+\s*[a-z]*\b"), confidence="medium"),
    # ponytail: backfill for Presidio removal — 3 entity types that were only covered by Presidio
    _Pattern("crypto_btc",      "crypto",      re.compile(r"\b(?:1[a-km-zA-HJ-NP-Z1-9]{25,34}|3[a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-zA-HJ-NP-Z0-9]{25,90})\b"), confidence="high"),
    _Pattern("crypto_eth",      "crypto",      re.compile(r"\b0x[0-9a-fA-F]{40}\b"), confidence="high"),
    _Pattern("us_bank_routing", "bank",        re.compile(r"(?i)(?:routing|aba|transit)\s*(?:number|num|no|#)?\s*[:=]?\s*([0-9]{9})\b"), confidence="high"),
    _Pattern("uk_nhs",          "nhs",         re.compile(r"(?i)(?:nhs|national\s*health)\s*(?:number|num|no|#)?\s*[:=]?\s*(\d{3}\s?\d{3}\s?\d{4})\b"), confidence="high"),
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
            elif p.name in ["phone_us", "phone_in"]:
                det_type = "phone number"
            elif p.name == "spelled_numbers":
                det_type = "ssn"
            elif p.name == "spelled_date":
                det_type = "date_time"
            elif p.name == "fake_cc":
                det_type = "credit_card"
            elif p.name in ["aadhar", "pan_card", "voter_id"]:
                det_type = "tax ID"
            elif p.name == "upi_id":
                det_type = "email"
            elif p.name in ["crypto_btc", "crypto_eth"]:
                det_type = "crypto wallet"
            elif p.name == "us_bank_routing":
                det_type = "US bank number"
            elif p.name == "uk_nhs":
                det_type = "UK NHS number"

            detections.append(Detection(
                start=m.start(),
                end=m.end(),
                type=det_type,
                subtype=p.subtype,
                confidence=p.confidence,
            ))
    return detections
