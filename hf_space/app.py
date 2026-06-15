import os
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
from gliner2 import GLiNER2
from presidio_analyzer import AnalyzerEngine
import logging

logger = logging.getLogger("pii_ml")
logger.setLevel(logging.INFO)

# Suppress GLiNER output
def _mock_print_config(self, config): pass
GLiNER2._print_config = _mock_print_config

app = FastAPI(title="PII ML API", description="HuggingFace Space for GLiNER and Presidio")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "PII ML API is running!"}

# Initialize models
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading GLiNER on {device}...")
gliner_model = GLiNER2.from_pretrained(
    "fastino/gliner2-privacy-filter-PII-multi",
    token=os.getenv("HF_TOKEN", None)
).to(device)

if device == "cpu":
    import torch.quantization
    gliner_model = torch.quantization.quantize_dynamic(
        gliner_model, {torch.nn.Linear}, dtype=torch.qint8
    )

print("Loading Presidio...")
presidio_analyzer = AnalyzerEngine()

print("Loading BAAI/bge-small-en-v1.5 for semantic embeddings...")
try:
    from sentence_transformers import SentenceTransformer
    semantic_model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    semantic_model.to(device)
except Exception as e:
    logger.error(f"Failed to load semantic model: {e}")
    semantic_model = None

class DetectRequest(BaseModel):
    text: str

class DetectResponse(BaseModel):
    detections: List[Dict[str, Any]]

class EmbeddingsRequest(BaseModel):
    inputs: List[str]

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

ENTITY_MAP = {
    "CREDIT_CARD": "credit card", "EMAIL_ADDRESS": "email", "PERSON": "person",
    "PHONE_NUMBER": "phone number", "IP_ADDRESS": "IP address", "IBAN_CODE": "IBAN code",
    "US_SSN": "US SSN", "LOCATION": "location", "URL": "URL", "DATE_TIME": "date time",
    "CRYPTO": "crypto wallet", "US_BANK_NUMBER": "US bank number", 
    "US_DRIVER_LICENSE": "US driver license", "US_ITIN": "US ITIN", 
    "US_PASSPORT": "US passport", "UK_NHS": "UK NHS number"
}

@app.post("/embeddings")
async def get_embeddings(req: EmbeddingsRequest):
    if not semantic_model:
        return {"error": "Semantic model failed to load"}
    
    try:
        # BAAI/bge-small-en-v1.5 produces list of vectors
        embeddings = semantic_model.encode(req.inputs, normalize_embeddings=True)
        return embeddings.tolist()
    except Exception as e:
        logger.error(f"Semantic embedding error: {e}")
        return {"error": str(e)}

@app.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    text = req.text
    if not text.strip():
        return {"detections": []}

    detections = []

    # --- GLiNER2 Detection ---
    try:
        extracted = gliner_model.extract_entities(text, LABELS, include_spans=True, include_confidence=True)
        all_predictions = []
        for label, items in extracted.get("entities", {}).items():
            if not items: continue
            for item in items:
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

            if conf >= threshold:
                detections.append({
                    "start": pred["start"],
                    "end": pred["end"],
                    "type": pred["label"],
                    "subtype": "gliner_dynamic",
                    "confidence": "high"
                })
    except Exception as e:
        logger.error(f"GLiNER error: {e}")

    # --- Presidio Detection ---
    try:
        results = presidio_analyzer.analyze(text=text, language='en')
        for res in results:
            confidence = "high"
            if res.score < 0.6: confidence = "low"
            elif res.score < 0.85: confidence = "medium"
            mapped_type = ENTITY_MAP.get(res.entity_type, res.entity_type.lower().replace("_", " "))
            detections.append({
                "start": res.start,
                "end": res.end,
                "type": mapped_type,
                "subtype": "presidio",
                "confidence": confidence
            })
    except Exception as e:
        logger.error(f"Presidio error: {e}")

    return {"detections": detections}
