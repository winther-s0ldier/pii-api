from typing import List, Tuple
from fastapi import HTTPException
from app.pipeline.base import Detection
from app.pipeline import regex_stage, entropy_stage, luhn_stage, code_stage
from app.config import TIER_BLOCK, TIER_REDACT, TIER_AUDIT, get_block_warning
import requests
import os
import logging

logger = logging.getLogger(__name__)
def _get_priority(type_str: str) -> int:
    if type_str in TIER_BLOCK:
        return 3
    if type_str in TIER_REDACT:
        return 2
    return 1

def _merge_spans(detections: List[Detection]) -> List[Detection]:
    """Merge overlapping detections so we don't double-redact the same span."""
    if not detections:
        return []
    sorted_d = sorted(detections, key=lambda d: d.start)
    merged: List[Detection] = [sorted_d[0]]
    for current in sorted_d[1:]:
        last = merged[-1]
        if current.start <= last.end:
            # Overlapping — extend the previous span, prioritize the most severe type
            last_prio = _get_priority(last.type)
            curr_prio = _get_priority(current.type)
            # If priorities are equal, prefer local engines over HF
            if last_prio == curr_prio:
                if last.engine != "hf" and current.engine == "hf":
                    winning_type, winning_subtype = last.type, last.subtype
                elif current.engine != "hf" and last.engine == "hf":
                    winning_type, winning_subtype = current.type, current.subtype
                else:
                    winning_type = last.type
                    winning_subtype = last.subtype
            else:
                winning_type = last.type if last_prio > curr_prio else current.type
                winning_subtype = last.subtype if last_prio > curr_prio else current.subtype

            merged[-1] = Detection(
                start=last.start,
                end=max(last.end, current.end),
                type=winning_type,
                subtype=winning_subtype,
                confidence="high" if "high" in (last.confidence, current.confidence) else "medium",
                engine=last.engine if winning_type == last.type else current.engine
            )
        else:
            merged.append(current)
    return merged

def _classify_tier(detections: List[Detection]) -> str:
    types = set(d.type for d in detections)
    if types & TIER_BLOCK:
        return "BLOCK"
    if types & TIER_REDACT:
        return "REDACT"
    if types:
        return "AUDIT"
    return "CLEAN"

def run(text: str, allowed_pii: List[str] = None, ignored_values: List[str] = None) -> Tuple[str, List[Detection], str]:
    """
    Run all stages in sequence.
    Returns (processed_text, list_of_detections, action_tier).
    """
    if allowed_pii is None:
        allowed_pii = []
    if ignored_values is None:
        ignored_values = []
        
    all_detections: List[Detection] = []
    
    all_detections.extend(regex_stage.detect(text))
    all_detections.extend(code_stage.detect(text))
    all_detections.extend(luhn_stage.detect(text))
    all_detections.extend(entropy_stage.detect(text))
    
    hf_space_url = os.getenv("HF_SPACE_URL")
    if hf_space_url:
        try:
            url = hf_space_url.rstrip("/") + "/detect"
            res = requests.post(url, json={"text": text}, timeout=15)
            if res.status_code == 200:
                data = res.json().get("detections", [])
                for d in data:
                    all_detections.append(
                        Detection(
                            start=d["start"],
                            end=d["end"],
                            type=d["type"],
                            subtype=d["subtype"],
                            confidence=d["confidence"],
                            engine="hf"
                        )
                    )
            else:
                logger.error(f"HF API returned {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"Failed to call HF Space: {e}")

    merged = _merge_spans(all_detections)
    
    # Filter out allowed PII, except for TIER_BLOCK items which are strictly locked
    filtered = []
    for d in merged:
        if d.type in TIER_BLOCK:
            filtered.append(d)
            continue
            
        if text[d.start:d.end] in ignored_values:
            continue
            
        if d.type in allowed_pii:
            continue
            
        # Whitelist heuristic: Ignore 'person' tags if they are part of a casual greeting
        if d.type == "person":
            context_window = text[max(0, d.start - 20):d.end + 20].lower()
            greetings = ["hi ", "hello ", "hey ", "my name is", "i am ", "i'm "]
            if any(g in context_window for g in greetings):
                continue
                
        filtered.append(d)
    
    action = _classify_tier(filtered)
    
    if action == "BLOCK":
        blocked_types = [d.type for d in filtered if d.type in TIER_BLOCK]
        primary_type = blocked_types[0] if blocked_types else "code"
        warning_msg = get_block_warning(primary_type)
        
        # We handle the HTTP exception at the router level, but we could also raise here
        # For clean architecture, we return the action and let main.py handle the response
        return "", filtered, "BLOCK"

    if action in ["REDACT", "AUDIT"]:
        # Replace spans from right to left to preserve indices
        result = text
        for d in sorted(filtered, key=lambda x: x.start, reverse=True):
            # Clean, anonymized label (e.g. "[PERSON]" instead of "[REDACTED:person]")
            clean_label = d.type.upper().replace(" ", "_")
            label = f"[{clean_label}]"
            result = result[: d.start] + label + result[d.end :]
        return result, filtered, action

    # CLEAN passes the text through unchanged
    return text, filtered, action
