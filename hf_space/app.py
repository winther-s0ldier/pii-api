import os
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
from gliner2 import GLiNER2
import logging

logger = logging.getLogger("pii_ml")
logger.setLevel(logging.INFO)

# ponytail: suppress GLiNER2's _print_config emoji that crashes Windows cp1252 consoles
def _mock_print_config(self, config): pass
GLiNER2._print_config = _mock_print_config

app = FastAPI(title="PII ML API")

@app.get("/")
def read_root():
    return {"status": "ok"}

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading GLiNER2 on {device}...")
gliner_model = GLiNER2.from_pretrained(
    "fastino/gliner2-privacy-filter-PII-multi",
    token=os.getenv("HF_TOKEN", None)
).to(device)

if device == "cpu":
    import torch.quantization
    gliner_model = torch.quantization.quantize_dynamic(
        gliner_model, {torch.nn.Linear}, dtype=torch.qint8
    )
print("GLiNER2 ready.")

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
    "password": "Secret passwords or digital keys",
}

class DetectRequest(BaseModel):
    text: str

class DetectResponse(BaseModel):
    detections: List[Dict[str, Any]]

@app.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    text = req.text
    if not text.strip():
        return {"detections": []}

    detections = []
    try:
        # ponytail: format_results=False bypasses _format_entity_dict deduplication bug
        # (engine.py line 878 dedupes by text string — "John" at pos 5 and 80 → only first kept)
        extracted = gliner_model.extract_entities(
            text, LABELS,
            format_results=False,
            include_spans=True,
            include_confidence=True,
        )
        all_predictions = []
        for label, items in extracted.get("entities", {}).items():
            if not items or not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                item["label"] = label
                all_predictions.append(item)

        anchor_labels = ["tax ID", "card number", "ssn"]
        has_anchor = any(p.get("confidence", 0) > 0.90 and p["label"] in anchor_labels for p in all_predictions)
        word_count = len(text.split())

        for pred in all_predictions:
            conf = pred.get("confidence", 1.0)
            threshold = 0.85
            if word_count < 5:
                threshold -= 0.15
            if has_anchor and pred["label"] in ["person", "physical address", "organization"]:
                threshold -= 0.10

            start = pred.get("start")
            end = pred.get("end")
            if start is None or end is None:
                continue

            if conf >= threshold:
                detections.append({
                    "start": start,
                    "end": end,
                    "type": pred["label"],
                    "subtype": "gliner_dynamic",
                    "confidence": "high",
                })
    except Exception as e:
        logger.error(f"GLiNER error: {e}")

    return {"detections": detections}
