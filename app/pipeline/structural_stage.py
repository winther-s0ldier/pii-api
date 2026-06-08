from typing import List
from gliner2 import GLiNER2
from app.pipeline.base import Detection
import re

# Suppress the GLiNER console output (which contains emojis and '========')
def _mock_print_config(self, config):
    pass
GLiNER2._print_config = _mock_print_config

# Load GLiNER2 PII model
# We load this globally so it stays in memory across requests
model = GLiNER2.from_pretrained("fastino/gliner2-privacy-filter-PII-multi")

# Map requested labels to descriptions for the extractor.
LABELS = {
    "person": "First, last, or full names of people",
    "location": "Physical addresses, cities, countries, or regions",
    "organization": "Companies, institutions, or business names",
    "email": "Email addresses",
    "phone number": "Telephone or mobile numbers",
    "physical address": "Street addresses or building locations",
    "passport number": "Government issued passport numbers",
    "driver's license": "Driver's license numbers",
    "tax ID": "Tax identification numbers",
    "ssn": "Social security numbers",
    "card number": "Credit or debit card numbers",
    "CVV": "Card verification value codes",
    "IBAN": "International Bank Account Numbers",
    "IP address": "IPv4 or IPv6 network addresses",
    "API keys": "Secret tokens, API keys, or access keys used for authentication",
    "password": "Secret passwords or digital keys"
}

def detect(text: str) -> List[Detection]:
    detections: List[Detection] = []
    
    # Extract entities based on the labels dictionary.
    extracted = model.extract_entities(text, LABELS, include_spans=True, include_confidence=True)
    
    entities_dict = extracted.get("entities", {})
    for label, items in entities_dict.items():
        if not items:
            continue
        for item in items:
            conf = item.get("confidence", 1.0)
            if conf < 0.85:
                continue
            detections.append(Detection(
                start=item["start"],
                end=item["end"],
                type=label, # e.g. "person"
                subtype="gliner",
                confidence="high"
            ))

    return detections
