import os
import requests
import numpy as np
import logging

logger = logging.getLogger(__name__)

BENIGN_ANCHORS = [
    "I am talking to a company or business.",
    "This is a corporate brand or organization.",
    "The weather is nice today.",
    "I read a book by the author.",
    "As stated by the author in the book.",
    "This is a generic conversational greeting."
]

_anchor_embeddings = None
_local_model = None

def get_embeddings(texts):
    global _local_model
    hf_space_url = os.getenv("HF_SPACE_URL")
    
    if hf_space_url:
        url = hf_space_url.rstrip("/") + "/embeddings"
        import time
        try:
            max_retries = 3
            for attempt in range(max_retries):
                resp = requests.post(
                    url,
                    json={"inputs": texts},
                    timeout=10
                )
                if resp.status_code == 503:
                    logger.warning(f"HF Space is likely waking up (503). Retrying in 5s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(5)
                    continue
                
                resp.raise_for_status()
                return np.array(resp.json())
        except Exception as e:
            logger.error(f"HF Space embeddings failed: {e}. Falling back to local model.")
            
    # Fallback disabled for production to prevent memory limit crashes
    logger.error("HF Space embeddings failed and local fallback is disabled. Returning None.")
    return None

def is_benign_context(text: str, threshold: float = 0.82) -> bool:
    global _anchor_embeddings
    if _anchor_embeddings is None:
        _anchor_embeddings = get_embeddings(BENIGN_ANCHORS)
    if _anchor_embeddings is None:
        return False
    # Lazy chunking by 300 words
    words = text.split()
    chunks = [" ".join(words[i:i+300]) for i in range(0, max(1, len(words)), 300)]
    
    embs = get_embeddings(chunks)
    if embs is None:
        return False
        
    for emb in embs:
        sims = np.dot(emb, _anchor_embeddings.T) / (np.linalg.norm(emb) * np.linalg.norm(_anchor_embeddings, axis=1))
        if np.max(sims) >= threshold:
            logger.info(f"Semantic filter matched benign context")
            return True
    return False
