"""
Self-check: verify _markdown_chunks offset logic and _parse_predictions shape.
No model load needed — mocks batch_extract_entities to test the plumbing.
Run from repo root: python hf_space/check_batch.py
"""
import sys
import re
from typing import List, Dict, Any

# ── copy the functions under test so we don't import the whole FastAPI app ──

CHUNK_CHARS = 1200

def _markdown_chunks(text: str) -> List[tuple]:
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

def _parse_predictions(extracted: Dict) -> List[Dict]:
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

def _apply_thresholds(predictions, chunk):
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
        start, end = pred.get("start"), pred.get("end")
        if start is None or end is None:
            continue
        if conf >= threshold:
            detections.append({"start": start, "end": end, "type": pred["label"],
                                "subtype": "gliner_dynamic", "confidence": "high"})
    return detections

# ── tests ────────────────────────────────────────────────────────────────────

ok = True

def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"  OK  {label}")
    else:
        print(f"  FAIL {label}" + (f": {detail}" if detail else ""))
        ok = False

# 1. short text → single chunk, zero offset
print("=== 1. short text stays one chunk ===")
t = "Hello world."
chunks = _markdown_chunks(t)
check("one chunk", len(chunks) == 1)
check("offset is 0", chunks[0][1] == 0)
check("text preserved", chunks[0][0] == t)

# 2. two paragraphs → two chunks when combined they'd exceed CHUNK_CHARS
print("\n=== 2. two large paragraphs split correctly ===")
para_a = "A " * 400          # 800 chars
para_b = "B " * 400          # 800 chars
text2 = para_a.rstrip() + "\n\n" + para_b.rstrip()
chunks2 = _markdown_chunks(text2)
check("split into 2 chunks", len(chunks2) == 2, f"got {len(chunks2)}")
check("chunk 0 starts at 0", chunks2[0][1] == 0)
# chunk 1 should start after para_a + separator
sep_pos = text2.index("\n\n")
check("chunk 1 offset >= sep position", chunks2[1][1] >= sep_pos, f"offset={chunks2[1][1]} sep={sep_pos}")

# 3. offset arithmetic: simulate two chunks at known offsets, verify spans map back correctly
print("\n=== 3. offset + local position = correct span in original ===")
part1 = "Contact Alice Smith at alice@corp.com for help."
part2 = "Call Bob Jones on +44 7700 900123 to confirm."
sep = "\n\n"
full_text = part1 + sep + part2
chunk0_off = 0
chunk1_off = len(part1) + len(sep)   # 49

# simulate batch returning local positions within each chunk
mock_batch = [
    {"entities": {"person": [{"start": 8, "end": 19, "confidence": 0.95}]}},   # "Alice Smith" in chunk0
    {"entities": {"person": [{"start": 5, "end": 14, "confidence": 0.95}]}},   # "Bob Jones" in chunk1
]
active = [(part1, chunk0_off), (part2, chunk1_off)]
all_detections = []
for result, (chunk_text, char_offset) in zip(mock_batch, active):
    preds = _parse_predictions(result)
    for d in _apply_thresholds(preds, chunk_text):
        d["start"] += char_offset
        d["end"] += char_offset
        all_detections.append(d)

check("two detections total", len(all_detections) == 2, f"got {len(all_detections)}")
d0, d1 = all_detections[0], all_detections[1]
check("span 0 resolves to 'Alice Smith'", full_text[d0["start"]:d0["end"]] == "Alice Smith",
      f"got '{full_text[d0['start']:d0['end']]}'")
check("span 1 resolves to 'Bob Jones'",  full_text[d1["start"]:d1["end"]] == "Bob Jones",
      f"got '{full_text[d1['start']:d1['end']]}'")
check("chunk 1 offset is correct", chunk1_off == 49, f"got {chunk1_off}")

# 4. hard-split: single paragraph over CHUNK_CHARS
print("\n=== 4. oversized single paragraph gets hard-split ===")
big = "word " * 400   # 2000 chars, no paragraph breaks
big_chunks = _markdown_chunks(big)
check("more than one chunk", len(big_chunks) > 1, f"got {len(big_chunks)}")
for i, (ct, off) in enumerate(big_chunks):
    check(f"chunk {i} within limit", len(ct) <= CHUNK_CHARS, f"len={len(ct)}")
# verify chunks reconstruct original (offsets are correct)
reconstructed = "".join(text for text, _ in big_chunks)
check("chunks reconstruct original", reconstructed == big.rstrip() or reconstructed == big)

# 5. confidence threshold filtering
print("\n=== 5. low-confidence prediction filtered out ===")
low_conf_result = {"entities": {"person": [{"start": 0, "end": 5, "confidence": 0.50}]}}
preds = _parse_predictions(low_conf_result)
dets = _apply_thresholds(preds, "Hello world this is a test sentence.")
check("low-conf detection dropped", len(dets) == 0, f"got {len(dets)}")

print(f"\n{'ALL OK' if ok else 'FAILURES -- see above'}")
sys.exit(0 if ok else 1)
