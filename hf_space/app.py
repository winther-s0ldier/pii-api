import os
import re
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

# ponytail: DeBERTa-v3 backbone hard limit is 512 tokens ≈ 1500 chars; 1200 leaves room for label tokens
CHUNK_CHARS = 1200

def _markdown_chunks(text: str) -> List[tuple]:
    """Split on markdown paragraph breaks, return (chunk_text, char_offset) pairs."""
    # Split keeping separators so we can track exact offsets
    parts = re.split(r'(\n{2,})', text)
    chunks, buf, buf_off, off = [], "", 0, 0
    for part in parts:
        if len(buf) + len(part) > CHUNK_CHARS and buf.strip():
            chunks.append((buf, buf_off))
            buf_off = off
            buf = part
        else:
            buf += part
        off += len(part)
    if buf.strip():
        chunks.append((buf, buf_off))

    # hard-split any chunk still over limit (e.g. a single huge paragraph)
    result = []
    for chunk, base in chunks:
        if len(chunk) <= CHUNK_CHARS:
            result.append((chunk, base))
            continue
        pos = 0
        while pos < len(chunk):
            end = min(pos + CHUNK_CHARS, len(chunk))
            if end < len(chunk):
                space = chunk.rfind(' ', pos, end)
                if space > pos:
                    end = space + 1
            result.append((chunk[pos:end], base + pos))
            pos = end

    return result or [(text, 0)]


def _apply_thresholds(predictions: List[Dict], chunk: str) -> List[Dict[str, Any]]:
    """Filter predictions by confidence threshold, return detection dicts."""
    anchor_labels = ["tax ID", "card number", "ssn"]
    has_anchor = any(p.get("confidence", 0) > 0.90 and p["label"] in anchor_labels for p in predictions)
    word_count = len(chunk.split())

    detections = []
    for pred in predictions:
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
    return detections


def _parse_predictions(extracted: Dict) -> List[Dict]:
    """Flatten format_results=False output into a list of prediction dicts.

    format_results=False returns {"entities": [OrderedDict(label -> [items])]},
    not {"entities": {label: [items]}} — the outer list must be iterated first.
    """
    predictions = []
    for entity_dict in extracted.get("entities", []):
        for label, items in entity_dict.items():
            if not items or not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                item["label"] = label
                predictions.append(item)
    return predictions


class DetectRequest(BaseModel):
    text: str

class DetectResponse(BaseModel):
    detections: List[Dict[str, Any]]

@app.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest):
    text = req.text
    if not text.strip():
        return {"detections": []}

    chunks = _markdown_chunks(text) if len(text) > CHUNK_CHARS else [(text, 0)]
    active_chunks = [(t, off) for t, off in chunks if t.strip()]

    all_detections = []
    try:
        chunk_texts = [t for t, _ in active_chunks]
        # ponytail: batch_extract_entities runs all chunks in one batched tensor op —
        # 166 sequential calls → ~11 batched passes at batch_size=16
        # format_results=False bypasses deduplication bug (engine.py:878)
        batch_results = gliner_model.batch_extract_entities(
            chunk_texts, LABELS,
            batch_size=16,
            format_results=False,
            include_spans=True,
            include_confidence=True,
        )
        for result, (chunk_text, char_offset) in zip(batch_results, active_chunks):
            predictions = _parse_predictions(result)
            for d in _apply_thresholds(predictions, chunk_text):
                d["start"] += char_offset
                d["end"] += char_offset
                all_detections.append(d)
    except Exception as e:
        logger.error(f"GLiNER error: {e}")

    return {"detections": all_detections}
