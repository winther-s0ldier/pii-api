from typing import List, Tuple
from fastapi import HTTPException
from app.pipeline.base import Detection
from app.pipeline import regex_stage, entropy_stage, luhn_stage, code_stage
from app.config import TIER_BLOCK, TIER_REDACT, TIER_AUDIT, get_block_warning
import requests
import os
import logging
import spacy

try:
    nlp = spacy.load("en_core_web_sm")
except (OSError, ImportError):
    nlp = None

logger = logging.getLogger(__name__)
def _get_priority(type_str: str, tier_config: dict = None) -> int:
    if tier_config is None:
        from app.config import TIER_BLOCK, TIER_REDACT
        if type_str in TIER_BLOCK:
            return 3
        if type_str in TIER_REDACT:
            return 2
        return 1
        
    if type_str in tier_config.get("block", set()):
        return 3
    if type_str in tier_config.get("redact", set()):
        return 2
    return 1

def _merge_spans(detections: List[Detection], tier_config: dict = None) -> List[Detection]:
    """Merge overlapping detections so we don't double-redact the same span."""
    if not detections:
        return []
    sorted_d = sorted(detections, key=lambda d: d.start)
    merged: List[Detection] = [sorted_d[0]]
    for current in sorted_d[1:]:
        last = merged[-1]
        if current.start <= last.end:
            # Overlapping — extend the previous span, prioritize the most severe type
            last_prio = _get_priority(last.type, tier_config)
            curr_prio = _get_priority(current.type, tier_config)
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

def _classify_tier(detections: List[Detection], tier_config: dict = None) -> str:
    types = set(d.type for d in detections)
    if tier_config is None:
        from app.config import TIER_BLOCK, TIER_REDACT
        block_set = TIER_BLOCK
        redact_set = TIER_REDACT
    else:
        block_set = tier_config.get("block", set())
        redact_set = tier_config.get("redact", set())
        
    if types & block_set:
        return "BLOCK"
    if types & redact_set:
        return "REDACT"
    if types:
        return "AUDIT"
    return "CLEAN"

def run(text: str, allowed_pii: List[str] = None, ignored_values: List[str] = None, tier_config: dict = None, custom_labels=None) -> Tuple[str, List[Detection], str]:
    """
    Run all stages in sequence.
    Returns (processed_text, list_of_detections, action_tier).
    """
    if allowed_pii is None:
        allowed_pii = []
    if ignored_values is None:
        ignored_values = []
    if custom_labels is None:
        custom_labels = []
        
    all_detections: List[Detection] = []
    
    all_detections.extend(regex_stage.detect(text))
    all_detections.extend(code_stage.detect(text))
    all_detections.extend(luhn_stage.detect(text))
    all_detections.extend(entropy_stage.detect(text))
    
    # Custom Labels (Dictionary and Regex)
    import json
    import re
    for cl in custom_labels:
        # Regex Matching
        if cl.regex_pattern:
            try:
                for match in re.finditer(cl.regex_pattern, text):
                    all_detections.append(Detection(
                        start=match.start(),
                        end=match.end(),
                        type=cl.name,
                        subtype="custom_regex",
                        confidence="high",
                        engine="custom"
                    ))
            except: pass
            
        # Dictionary Matching
        if cl.dictionary_words:
            try:
                words = json.loads(cl.dictionary_words)
                text_lower = text.lower()
                for w in words:
                    if not w.strip(): continue
                    w_lower = w.strip().lower()
                    start = 0
                    while True:
                        start = text_lower.find(w_lower, start)
                        if start == -1: break
                        all_detections.append(Detection(
                            start=start,
                            end=start + len(w_lower),
                            type=cl.name,
                            subtype="custom_dict",
                            confidence="high",
                            engine="custom"
                        ))
                        start += len(w_lower)
            except: pass
    
    # Determine GLiNER labels
    gliner_labels = ["person", "organization", "location", "email address", "phone number"]
    # We DO NOT add custom labels to GLiNER. Custom labels are strictly rule-based (Regex/Dictionary).
            
    hf_space_url = os.getenv("HF_SPACE_URL")
    if hf_space_url:
        try:
            url = hf_space_url.rstrip("/") + "/detect"
            # We can optionally pass labels if the HF space supports it, but for now we just pass text
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
    else:
        # Fallback to local GLiNER if installed
        try:
            from gliner import GLiNER
            # Load a small fast model for local dev if not loaded
            if not hasattr(run, "gliner_model"):
                run.gliner_model = GLiNER.from_pretrained("urchade/gliner_tiny")
            
            entities = run.gliner_model.predict_entities(text, gliner_labels, threshold=0.5)
            for ent in entities:
                all_detections.append(
                    Detection(
                        start=ent["start"],
                        end=ent["end"],
                        type=ent["label"],
                        subtype="gliner",
                        confidence="high" if ent["score"] > 0.8 else "medium",
                        engine="local_gliner"
                    )
                )
        except ImportError:
            pass


    merged = _merge_spans(all_detections, tier_config)
    
    if tier_config is None:
        from app.config import TIER_BLOCK
        block_set = TIER_BLOCK
    else:
        block_set = tier_config.get("block", set())

    # Filter out allowed PII, except for TIER_BLOCK items which are strictly locked
    filtered = []
    for d in merged:
        if d.type in block_set:
            filtered.append(d)
            continue
            
        if text[d.start:d.end] in ignored_values:
            continue
            
        if d.type in allowed_pii:
            continue
            
        if d.type == "person":
            context_window = text[max(0, d.start - 20):d.end + 20].lower()
            greetings = ["hi ", "hello ", "hey ", "my name is", "i am ", "i'm "]
            if any(g in context_window for g in greetings):
                continue
                
        if d.type in ["location", "date_time", "date", "time", "GPE", "LOC", "DATE", "TIME"]:
            if nlp:
                doc = nlp(text)
                weather_terms = {"weather", "forecast", "temperature", "raining", "sunny"}
                is_weather_context = False
                
                # Find tokens that overlap with the detection
                for token in doc:
                    # token.idx is the start char offset
                    if token.idx >= d.start and token.idx < d.end:
                        # Check if any ancestor (e.g. parent verb/noun) is a weather term
                        # Or if the head of this token has a weather term as a child (siblings in dependency tree)
                        if any(anc.text.lower() in weather_terms for anc in token.ancestors) or \
                           any(child.text.lower() in weather_terms for child in token.head.children) or \
                           token.head.text.lower() in weather_terms:
                            is_weather_context = True
                            break
                            
                if is_weather_context:
                    continue
            else:
                # Fallback to simple keyword check if spaCy model isn't downloaded yet
                context_window = text[max(0, d.start - 40):d.end + 40].lower()
                weather_terms = ["weather", "forecast", "temperature", "raining", "sunny", "time is"]
                if any(w in context_window for w in weather_terms):
                    continue
                
        filtered.append(d)
    
    action = _classify_tier(filtered, tier_config)
    
    if action == "BLOCK":
        blocked_types = [d.type for d in filtered if d.type in block_set]
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
