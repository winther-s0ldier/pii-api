import os

ENTROPY_THRESHOLD_BASE64 = float(os.getenv("PI_ENTROPY_BASE64", "4.5"))
ENTROPY_THRESHOLD_HEX    = float(os.getenv("PI_ENTROPY_HEX", "3.0"))
ENTROPY_THRESHOLD_OTHER  = float(os.getenv("PI_ENTROPY_OTHER", "4.0"))
ENTROPY_MIN_LENGTH       = int(os.getenv("PI_ENTROPY_MIN_LEN", "20"))
MAX_MESSAGE_LENGTH       = int(os.getenv("PI_MAX_MSG_LEN", "10000"))
CODE_DENSITY_THRESHOLD   = int(os.getenv("PI_CODE_DENSITY", "2"))

TIER_BLOCK = {
    "api_key", "credit_card", "code", "private_key",
    "card number", "CVV", "IBAN", "API keys", "password"
}

TIER_REDACT = {
    "ssn",
    "passport number", "driver's license", "tax ID"
}

TIER_AUDIT = {
    "email", "full_name", "person", "location", "organization",
    "phone number", "physical address", "IP address"
}

def get_block_warning(detection_type: str) -> str:
    if detection_type == "api_key":
        return "Security Alert: An API key was detected. Please rotate it immediately."
    elif detection_type == "credit_card":
        return "Security Alert: Credit card information is not permitted."
    elif detection_type == "code":
        return "Security Alert: Code injection detected. Request blocked."
    return "Security Alert: High-risk credentials detected. Request blocked."
