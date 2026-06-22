"""
Empirical verification of the audit findings. Runs the real pipeline rule stages
(HF_SPACE_URL unset -> GLiNER skipped, so we isolate regex/luhn/entropy/code).
Run from repo root: venv\\Scripts\\python tests\\audit_check.py
"""
import os
os.environ.pop("HF_SPACE_URL", None)  # isolate local rules, no GLiNER

from app.pipeline import pipeline, regex_stage, code_stage, entropy_stage, luhn_stage

def show(label, text):
    processed, dets, action = pipeline.run(text)
    types = sorted(set(d.type for d in dets))
    print(f"\n[{label}] action={action}")
    print(f"  input : {text!r}")
    print(f"  types : {types}")
    return action, types

print("=" * 70)
print("FINDING #1 — common English words -> code BLOCK")
show("cat+cut prose", "I adopted a cat and had to cut my monthly budget.")
show("cat+cut+grep",  "The cat will cut through grep results quickly.")
# raw stage view
hits = code_stage.detect("I adopted a cat and had to cut my budget")
print(f"  code_stage raw hits: {len(hits)} (threshold triggers at >=2)")

print("=" * 70)
print("FINDING #2 — bare 15-16 digit -> credit_card BLOCK (no Luhn)")
show("imei 15-digit",   "My device IMEI is 490154203237518.")
show("order 16-digit",  "Order number 1234567890123456 shipped today.")
luhn_hits = luhn_stage.detect("1234567890123456")
print(f"  luhn_stage on that 16-digit: {len(luhn_hits)} (0 = not a valid card)")

print("=" * 70)
print("FINDING #3 — shebang regex broken")
import re
shebang_sig = code_stage._SIGNATURES[3]
print(f"  pattern: {shebang_sig.pattern}")
print(f"  matches '#!/usr/bin/bash' ? {bool(shebang_sig.search('#!/usr/bin/bash'))}  (should be True)")
print(f"  matches '#!/wwww'        ? {bool(shebang_sig.search('#!/wwww'))}  (proves bug)")

print("=" * 70)
print("MUST-CATCH (fixes must not break real detections)")
show("valid visa card", "Pay with 4111 1111 1111 1111 today.")   # luhn-valid -> credit_card
show("dashed card",     "Card 4111-1111-1111-1111 on file.")
show("us phone dashed", "Call me at 415-555-0123 tomorrow.")
show("us phone parens", "Reach us at (415) 555-0123.")
show("ssn standard",    "SSN 123-45-6789 on the form.")
show("real shell",      "Run cat /etc/passwd | grep root to see it.")

print("=" * 70)
print("EXTRA probes")
show("phone spacing",   "Values:\n1\n2\n3\n4\n5\n6\n7\n8\n9\n0")
show("ssn spacing",     "1 2 3 - 4 5 - 6 7 8 9")
show("uuid",            "Session id 550e8400-e29b-41d4-a716-446655440000 expired.")
show("clean control",   "Thanks for the update, looking forward to the meeting next week.")

print("=" * 70)
print("GUARD — hard assertions (exit nonzero if any fix regresses)")

def act(text):
    return pipeline.run(text)[2]
def types_of(text):
    return set(d.type for d in pipeline.run(text)[1])

checks = [
    # (description, condition)
    ("prose cat/cut not blocked",      act("I adopted a cat and had to cut my monthly budget.") == "CLEAN"),
    ("prose cat/cut/grep not blocked", act("The cat will cut through grep results quickly.") == "CLEAN"),
    ("random 16-digit not a card",     "credit_card" not in types_of("Order number 1234567890123456 shipped today.")),
    ("digit column not a phone",       "phone number" not in types_of("Values:\n1\n2\n3\n4\n5\n6\n7\n8\n9\n0")),
    ("shebang matched",                bool(code_stage._SIGNATURES[3].search("#!/usr/bin/bash"))),
    # must-catch (fixes must not weaken real detection)
    ("visa card still caught",         "credit_card" in types_of("Pay with 4111 1111 1111 1111 today.")),
    ("dashed card still caught",       "credit_card" in types_of("Card 4111-1111-1111-1111 on file.")),
    ("us phone still caught",          "phone number" in types_of("Call me at 415-555-0123 tomorrow.")),
    ("standard ssn still caught",      "ssn" in types_of("SSN 123-45-6789 on the form.")),
    ("real shell still blocked",       act("Run cat /etc/passwd | grep root to see it.") == "BLOCK"),
]

import sys
ok = True
for desc, cond in checks:
    print(f"  {'OK  ' if cond else 'FAIL'} {desc}")
    ok = ok and cond
print("\n" + ("ALL GUARDS PASS" if ok else "GUARD FAILURE"))
sys.exit(0 if ok else 1)
