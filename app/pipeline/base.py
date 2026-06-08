from dataclasses import dataclass


@dataclass
class Detection:
    start: int
    end: int
    type: str
    subtype: str
    confidence: str 
