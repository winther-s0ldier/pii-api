from typing import List
from presidio_analyzer import AnalyzerEngine
from app.pipeline.base import Detection
import logging

logger = logging.getLogger(__name__)

# Initialize AnalyzerEngine as a singleton to avoid reloading models on every request
analyzer = None

def get_analyzer():
    global analyzer
    if analyzer is None:
        logger.info("Initializing Presidio AnalyzerEngine...")
        analyzer = AnalyzerEngine()
    return analyzer

# Map Presidio entity types to our schema
ENTITY_MAP = {
    "CREDIT_CARD": "credit card",
    "EMAIL_ADDRESS": "email",
    "PERSON": "person",
    "PHONE_NUMBER": "phone number",
    "IP_ADDRESS": "IP address",
    "IBAN_CODE": "IBAN code",
    "US_SSN": "US SSN",
    "LOCATION": "location",
    "URL": "URL",
    "DATE_TIME": "date time",
    "CRYPTO": "crypto wallet",
    "US_BANK_NUMBER": "US bank number",
    "US_DRIVER_LICENSE": "US driver license",
    "US_ITIN": "US ITIN",
    "US_PASSPORT": "US passport",
    "UK_NHS": "UK NHS number"
}

def detect(text: str) -> List[Detection]:
    if not text.strip():
        return []
        
    engine = get_analyzer()
    
    # We detect all supported entities
    try:
        results = engine.analyze(text=text, language='en')
    except Exception as e:
        logger.error(f"Presidio analyze error: {e}")
        return []

    detections = []
    for res in results:
        # Presidio score is 0.0 to 1.0
        confidence = "high"
        if res.score < 0.6:
            confidence = "low"
        elif res.score < 0.85:
            confidence = "medium"
            
        mapped_type = ENTITY_MAP.get(res.entity_type, res.entity_type.lower().replace("_", " "))
        
        detections.append(
            Detection(
                start=res.start,
                end=res.end,
                type=mapped_type,
                subtype="presidio",
                confidence=confidence
            )
        )
    return detections
