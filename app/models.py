from typing import List
from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10_000)


class RedactedType(BaseModel):
    type: str
    subtype: str
    confidence: str


class CheckResponse(BaseModel):
    action: str
    was_redacted: bool
    message: str
    redacted_types: List[RedactedType] = []

class BlockResponse(BaseModel):
    action: str = "BLOCK"
    warning: str
    blocked_types: List[RedactedType] = []
