from typing import List
from gliner2 import GLiNER2
from app.pipeline.base import Detection
import re

# Suppress the GLiNER console output (which contains emojis and '========')
def _mock_print_config(self, config):
    pass
GLiNER2._print_config = _mock_print_config

import torch

# Load GLiNER2 PII model
# We load this globally so it stays in memory across requests
device = "cuda" if torch.cuda.is_available() else "cpu"
model = GLiNER2.from_pretrained("fastino/gliner2-privacy-filter-PII-multi").to(device)

if device == "cpu":
    import torch.quantization
    # Apply dynamic quantization to Linear layers for 2x-4x CPU speedup
    model = torch.quantization.quantize_dynamic(
        model, {torch.nn.Linear}, dtype=torch.qint8
    )

# Map requested labels to descriptions for the extractor.
LABELS = {
    "person": "First, last, or full names of people, including Indian names",
    "location": "Physical addresses, cities, countries, or regions",
    "organization": "Companies, institutions, or business names",
    "email": "Email addresses",
    "phone number": "Telephone or mobile numbers",
    "physical address": "Street addresses, building locations, landmarks, or 6-digit Pincodes",
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
    
    # Extract entities based on the labels dictionary. We include all confidences first (threshold=0.0).
    # Note: flat thresholding isn't supported directly via a threshold arg in all GLiNER versions in extract_entities,
    # so we'll just parse whatever it returns. The default usually returns everything or uses a low threshold.
    extracted = model.extract_entities(text, LABELS, include_spans=True, include_confidence=True)
    
    all_predictions = []
    entities_dict = extracted.get("entities", {})
    for label, items in entities_dict.items():
        if not items:
            continue
        for item in items:
            item["label"] = label
            all_predictions.append(item)
            
    # Find our "Anchor" entities (Things the model is 90%+ certain about)
    # Includes tax ID to anchor on PAN / Aadhaar cards
    anchor_labels = ["tax ID", "card number", "ssn"]
    has_high_confidence_anchor = any(p.get("confidence", 0) > 0.90 and p["label"] in anchor_labels for p in all_predictions)
    
    # Calculate text length to penalize lack of context
    word_count = len(text.split())

    for pred in all_predictions:
        conf = pred.get("confidence", 1.0)
        
        # Start with a strict base threshold
        dynamic_threshold = 0.85 
        
        # Condition A: If the text is extremely short, the model lacks context. Give it some grace.
        if word_count < 5:
            dynamic_threshold -= 0.15  # Drops to 0.70
            
        # Condition B: If there is a highly sensitive Anchor entity in this text, 
        # other nearby nouns are highly likely to be PII as well.
        if has_high_confidence_anchor and pred["label"] in ["person", "physical address", "organization"]:
            dynamic_threshold -= 0.10  # Drops further to catch contextually linked data
            
        # Only append if it passes the new, dynamically calculated threshold
        if conf >= dynamic_threshold:
            detections.append(Detection(
                start=pred["start"],
                end=pred["end"],
                type=pred["label"],
                subtype="gliner_dynamic",
                confidence="high"
            ))

    return detections
