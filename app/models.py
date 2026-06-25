from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    user_id: str = Field(default="00000000-0000-0000-0000-000000000000")
    session_id: str = Field(default="default_session")
    message: str = Field(..., min_length=1, max_length=5_000_000)
    allowed_pii: List[str] = Field(default=[])
    ignored_values: List[str] = Field(default=[])
    model: Optional[str] = Field(default=None, description="LLM model id to use for this message")


class CustomEndpoint(BaseModel):
    base_url: str
    api_key: Optional[str] = None
    model_name: str
    display_name: Optional[str] = None


class OrgModelConfig(BaseModel):
    default_model: Optional[str] = None
    allowed_models: List[str] = Field(default_factory=list)
    custom_endpoint: Optional[CustomEndpoint] = None


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: List[str] = Field(default_factory=lambda: ["check"])
    expires_in_days: Optional[int] = None
    rate_limit_per_min: int = Field(default=60, ge=1, le=10000)


class ApiKeyInfo(BaseModel):
    id: str
    name: str
    prefix: str
    scopes: List[str]
    rate_limit_per_min: int = 60
    last_used_at: Optional[datetime] = None
    last_used_ip: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime


class ApiKeyCreated(ApiKeyInfo):
    key: str  # full key, returned ONCE on creation


class RedactedType(BaseModel):
    type: str
    subtype: str
    confidence: Union[float, str]
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
    model_used: Optional[str] = None

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
    total_tokens: int = 0
    tokens_incomplete: bool = False

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

