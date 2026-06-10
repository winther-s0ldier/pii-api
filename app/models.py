from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    user_id: str = Field(default="default_user")
    session_id: str = Field(default="default_session")
    message: str = Field(..., min_length=1, max_length=10_000)
    allowed_pii: List[str] = Field(default=[])
    ignored_values: List[str] = Field(default=[])


class RedactedType(BaseModel):
    type: str
    subtype: str
    confidence: str
    value: str = ""


class CheckResponse(BaseModel):
    action: str
    was_redacted: bool
    message: str
    llm_reply: str = ""
    redacted_types: List[RedactedType] = []

class BlockResponse(BaseModel):
    action: str = "BLOCK"
    warning: str
    blocked_types: List[RedactedType] = []

class BatchCheckRequest(BaseModel):
    user_id: str = Field(default="default_user")
    messages: List[str] = Field(..., max_length=100, description="Up to 100 messages per batch")
    allowed_pii: List[str] = Field(default=[])

from typing import Union

class CheckResult(BaseModel):
    status: str = "success"
    action: str
    was_redacted: bool
    message: str
    redacted_types: List[RedactedType] = []

class BlockResult(BaseModel):
    status: str = "blocked"
    action: str = "BLOCK"
    warning: str
    blocked_types: List[RedactedType] = []

BatchCheckResult = Union[CheckResult, BlockResult]

class BatchCheckResponse(BaseModel):
    results: List[BatchCheckResult]

from datetime import datetime

class ChatSessionInfo(BaseModel):
    id: str
    title: str
    created_at: datetime

class SessionListResponse(BaseModel):
    sessions: List[ChatSessionInfo]

class ChatMessageInfo(BaseModel):
    role: str
    content: str
    created_at: datetime
    redacted_types: Optional[List[Dict[str, Any]]] = None

class SessionDetailResponse(BaseModel):
    id: str
    title: str
    messages: List[ChatMessageInfo]

class TierConfigUpdate(BaseModel):
    tier_block: List[str] = []
    tier_redact: List[str] = []
    tier_audit: List[str] = []

class TierConfigResponse(BaseModel):
    user_id: str
    tier_block: List[str]
    tier_redact: List[str]
    tier_audit: List[str]

class StatCount(BaseModel):
    name: str
    count: int

class StatsResponse(BaseModel):
    total_requests: int
    actions: List[StatCount]
    detected_types: List[StatCount]
    top_sequences: List[StatCount] = Field(default_factory=list)

class CustomLabelBase(BaseModel):
    name: str
    description: str
    tier: str
    regex_pattern: Union[str, None] = None
    dictionary_words: List[str] = Field(default_factory=list)

class CustomLabelCreate(CustomLabelBase):
    pass

class CustomLabelResponse(CustomLabelBase):
    id: int
    created_at: datetime

