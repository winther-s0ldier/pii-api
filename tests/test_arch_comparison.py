import os
import sys
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.pipeline import pipeline

# These are classic edge cases where GLiNER hallucinates PII because it doesn't
# understand the broader benign context (e.g. John Deere is a company, Dell is a brand, LA is just weather chat).
TEST_CASES = [
    "I am talking to a company or business called John Deere about their new tractor models.",
    "This is a corporate brand or organization, specifically Dell Computers.",
    "The weather is nice today, and I am visiting Los Angeles for a vacation."
]

print("=== RUNNING WITHOUT BGE-SMALL SEMANTIC FILTER (Current Architecture) ===")
os.environ["USE_SEMANTIC_FILTER"] = "False"
for i, text in enumerate(TEST_CASES):
    print(f"\nTest Case {i+1}: '{text}'")
    start = time.time()
    processed_text, detections, action = pipeline.run(text)
    duration = time.time() - start
    print(f"Action: {action} in {duration:.2f}s")
    for d in detections:
        print(f"  - Detected {d.type} ({d.subtype}): '{text[d.start:d.end]}'")

print("\n\n=== RUNNING WITH BGE-SMALL SEMANTIC FILTER (New Architecture) ===")
os.environ["USE_SEMANTIC_FILTER"] = "True"
for i, text in enumerate(TEST_CASES):
    print(f"\nTest Case {i+1}: '{text}'")
    start = time.time()
    processed_text, detections, action = pipeline.run(text)
    duration = time.time() - start
    print(f"Action: {action} in {duration:.2f}s")
    for d in detections:
        print(f"  - Detected {d.type} ({d.subtype}): '{text[d.start:d.end]}'")
