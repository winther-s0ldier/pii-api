from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.models import CheckRequest, CheckResponse, BlockResponse, RedactedType
from app.pipeline import pipeline
from app.pipeline import regex_stage
from app.config import get_block_warning

app = FastAPI(
    title="PI Detection API",
    description="Detects and redacts Personal Information from messages before they reach a downstream bot.",
)

@app.post("/api/v1/check", response_model=CheckResponse)
def check_message(body: CheckRequest):
    processed_text, detections, action = pipeline.run(body.message)
    
    redacted_types = [
        RedactedType(type=d.type, subtype=d.subtype, confidence=d.confidence)
        for d in detections
    ]
    
    if action == "BLOCK":
        # Determine primary blocked type for the warning message
        from app.config import TIER_BLOCK
        blocked_types = [d.type for d in detections if d.type in TIER_BLOCK]
        primary_type = blocked_types[0] if blocked_types else "code"
        
        raise HTTPException(
            status_code=400,
            detail=BlockResponse(
                action="BLOCK",
                warning=get_block_warning(primary_type),
                blocked_types=redacted_types
            ).model_dump()
        )

    return CheckResponse(
        action=action,
        was_redacted=(action == "REDACT"),
        message=processed_text,
        redacted_types=redacted_types
    )

from app.models import BatchCheckRequest, BatchCheckResponse, CheckResult, BlockResult

@app.post("/api/v1/check_batch", response_model=BatchCheckResponse)
def check_message_batch(body: BatchCheckRequest):
    from app.config import TIER_BLOCK
    results = []
    for msg in body.messages:
        processed_text, detections, action = pipeline.run(msg)
        
        redacted_types = [
            RedactedType(type=d.type, subtype=d.subtype, confidence=d.confidence)
            for d in detections
        ]
        
        if action == "BLOCK":
            blocked_types = [d.type for d in detections if d.type in TIER_BLOCK]
            primary_type = blocked_types[0] if blocked_types else "code"
            
            results.append(BlockResult(
                action="BLOCK",
                warning=get_block_warning(primary_type),
                blocked_types=redacted_types
            ))
        else:
            results.append(CheckResult(
                action=action,
                was_redacted=(action == "REDACT"),
                message=processed_text,
                redacted_types=redacted_types
            ))
            
    return BatchCheckResponse(results=results)
@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/patterns")
def list_patterns():
    return {
        "stages": [
            "regex_recognisers",
            "structural_recognisers",
            "entropy_analyser",
            "luhn_validator",
        ],
        "regex_patterns": [p.name for p in regex_stage._PATTERNS],
    }
