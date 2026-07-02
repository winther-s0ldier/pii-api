from typing import List, Tuple
from app.pipeline.base import Detection
from app.pipeline import regex_stage, entropy_stage, luhn_stage, code_stage, context_stage
from app.config import TIER_BLOCK, TIER_REDACT, TIER_AUDIT, get_block_warning
import requests
import os
import logging
import json

logger = logging.getLogger(__name__)

def _hf_detect(url: str, text: str) -> str:
    # ponytail: lru_cache removed — keying on raw text stored PII (SSNs, card numbers)
    # in process memory across requests; cross-user data exposure risk
    res = requests.post(url + "/detect", json={"text": text}, timeout=60)
    if res.status_code != 200:
        raise RuntimeError(f"HF {res.status_code}")
    return res.text
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
            last_prio = _get_priority(last.type, tier_config)
            curr_prio = _get_priority(current.type, tier_config)
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
    import string
    clean_text = text.strip().lower().translate(str.maketrans('', '', string.punctuation))
    fast_bypass_words = {"hi", "hello", "hey", "sup", "howdy", "greetings", "good morning", "good afternoon", "good evening", "ok", "okay", "yes", "no", "thanks", "thank you", "bye", "goodbye", "ping"}
    if clean_text in fast_bypass_words:
        return text, [], "CLEAN"

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
    
    import re
    for cl in custom_labels:
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
            except Exception: pass
            
        if cl.dictionary_words:
            try:
                words = json.loads(cl.dictionary_words)
                text_lower = text.lower()
                for w in words:
                    if not w.strip(): continue
                    w_lower = w.strip().lower()
                    for match in re.finditer(r'\b' + re.escape(w_lower) + r'\b', text_lower):
                        all_detections.append(Detection(
                            start=match.start(),
                            end=match.end(),
                            type=cl.name,
                            subtype="custom_dict",
                            confidence="high",
                            engine="custom"
                        ))
            except Exception: pass
    
    if tier_config is None:
        from app.config import TIER_BLOCK, TIER_REDACT, TIER_AUDIT
        gliner_labels = list(TIER_BLOCK | TIER_REDACT | TIER_AUDIT)
    else:
        gliner_labels = list(set(tier_config.get("block", [])) | set(tier_config.get("redact", [])) | set(tier_config.get("audit", [])))

    # ponytail: skip HF entirely if local stages already found a BLOCK-tier type — saves 2-10s per blocked message
    _quick_block = TIER_BLOCK if tier_config is None else tier_config.get("block", set())
    if any(d.type in _quick_block for d in all_detections):
        merged = _merge_spans(all_detections, tier_config)
        filtered = [d for d in merged if d.type in _quick_block]
        return "", filtered, "BLOCK"

    # ponytail: semantic pre-filter removed — /embeddings endpoint dropped from HF Space
    hf_space_url = os.getenv("HF_SPACE_URL")
    hf_success = False
    if hf_space_url and len(text) >= 40:
        import time
        for attempt in range(2):
            try:
                data = json.loads(_hf_detect(hf_space_url.rstrip("/"), text)).get("detections", [])
                for d in data:
                    all_detections.append(Detection(
                        start=d["start"], end=d["end"],
                        type=d["type"], subtype=d["subtype"],
                        confidence=d["confidence"], engine="hf"
                    ))
                hf_success = True
                break
            except Exception as e:
                logger.warning(f"HF Space unavailable (attempt {attempt+1}/2): {e}")
                if attempt == 0:
                    time.sleep(3)

    if not hf_success:
        logger.warning("HF API unavailable. Using regex/rules only.")


    merged = _merge_spans(all_detections, tier_config)
    
    if tier_config is None:
        from app.config import TIER_BLOCK
        block_set = TIER_BLOCK
    else:
        block_set = tier_config.get("block", set())

    filtered = []
    for d in merged:
        if d.type in block_set:
            # Never drop BLOCK-tier detections on context — too risky
            filtered.append(d)
            continue

        if text[d.start:d.end] in ignored_values:
            continue

        if d.type in allowed_pii:
            continue

        if not context_stage.should_keep(text, d):
            continue

        filtered.append(d)
    
    action = _classify_tier(filtered, tier_config)
    
    if action == "BLOCK":
        blocked_types = [d.type for d in filtered if d.type in block_set]
        primary_type = blocked_types[0] if blocked_types else "code"
        warning_msg = get_block_warning(primary_type)
        
        return "", filtered, "BLOCK"

    if action in ["REDACT", "AUDIT"]:
        result = text
        for d in sorted(filtered, key=lambda x: x.start, reverse=True):
            clean_label = d.type.upper().replace(" ", "_")
            label = f"[{clean_label}]"
            result = result[: d.start] + label + result[d.end :]
        return result, filtered, action

    return text, filtered, action
