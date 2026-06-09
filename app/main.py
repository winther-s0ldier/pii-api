from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from google import genai
import os
from dotenv import load_dotenv
load_dotenv(override=True)

from app.models import CheckRequest, CheckResponse, BlockResponse, RedactedType, SessionListResponse, SessionDetailResponse, ChatSessionInfo, ChatMessageInfo
from app.pipeline import pipeline
from app.pipeline import regex_stage
from app.config import get_block_warning
from app.db import init_db, get_db, ChatSession, ChatMessage

app = FastAPI(
    title="PII Detection API",
    description="API for detecting and anonymizing PII data",
)

init_db()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def read_root():
    return FileResponse("frontend/index.html")

@app.post("/api/v1/check")
async def check_message(body: CheckRequest, db: Session = Depends(get_db)):
    import asyncio
    import json
    from fastapi.responses import StreamingResponse
    from app.config import TIER_BLOCK

    # 1. Async Pipeline Check
    processed_text, detections, action = await asyncio.to_thread(pipeline.run, body.message)
    
    redacted_types_dicts = [
        {
            "type": d.type, 
            "subtype": d.subtype, 
            "confidence": d.confidence,
            "value": body.message[d.start:d.end]
        }
        for d in detections
    ]
    
    if action == "BLOCK":
        blocked_types = [d.type for d in detections if d.type in TIER_BLOCK]
        primary_type = blocked_types[0] if blocked_types else "code"
        
        raise HTTPException(
            status_code=400,
            detail=BlockResponse(
                action="BLOCK",
                warning=get_block_warning(primary_type),
                blocked_types=[RedactedType(**rt) for rt in redacted_types_dicts]
            ).model_dump()
        )

    # 2. Database & LLM Integration
    session_id = body.session_id
    db_session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not db_session:
        title = body.message[:30] + "..." if len(body.message) > 30 else body.message
        db_session = ChatSession(id=session_id, title=title)
        db.add(db_session)
        db.commit()

    user_msg = ChatMessage(session_id=session_id, role="user", content=processed_text)
    db.add(user_msg)
    db.commit()

    async def generate():
        # First chunk: Metadata
        metadata = {
            "type": "metadata",
            "action": action,
            "message": processed_text,
            "redacted_types": redacted_types_dicts
        }
        yield f"data: {json.dumps(metadata)}\n\n"

        llm_reply = ""
        api_key = os.getenv("GEMINI_API_KEY", "").strip('"').strip("'")
        if api_key:
            history = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
            gemini_history = []
            for msg in history[:-1]:
                gemini_history.append({"role": msg.role, "parts": [{"text": msg.content}]})
                
            try:
                client = genai.Client(api_key=api_key)
                chat = client.aio.chats.create(model="gemini-3.1-pro-preview", history=gemini_history)
                response_stream = await chat.send_message_stream(processed_text)
                async for chunk in response_stream:
                    if chunk.text:
                        llm_reply += chunk.text
                        yield f"data: {json.dumps({'type': 'chunk', 'text': chunk.text})}\n\n"
                        
                model_msg = ChatMessage(session_id=session_id, role="model", content=llm_reply)
                db.add(model_msg)
                db.commit()
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'text': f'Error calling Gemini: {str(e)}'})}\n\n"
        else:
            llm_reply = "I am the pseudo LLM. I received your message securely. (Gemini API key not found in .env)"
            yield f"data: {json.dumps({'type': 'chunk', 'text': llm_reply})}\n\n"
            
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/v1/sessions", response_model=SessionListResponse)
def get_sessions(db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).order_by(ChatSession.created_at.desc()).all()
    return SessionListResponse(
        sessions=[ChatSessionInfo(id=s.id, title=s.title, created_at=s.created_at) for s in sessions]
    )

@app.get("/api/v1/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    return SessionDetailResponse(
        id=session.id,
        title=session.title,
        messages=[ChatMessageInfo(role=m.role, content=m.content, created_at=m.created_at) for m in messages]
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
