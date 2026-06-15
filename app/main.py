from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
from google import genai
import os
from dotenv import load_dotenv
load_dotenv(override=True)

from app.models import (
    CheckRequest, CheckResponse, BlockResponse, RedactedType,
    SessionListResponse, SessionDetailResponse, ChatSessionInfo, ChatMessageInfo,
    TierConfigUpdate, TierConfigResponse, StatsResponse, StatCount
)
from app.pipeline import pipeline
from app.pipeline import regex_stage
from app.config import get_block_warning, TIER_BLOCK, TIER_REDACT, TIER_AUDIT
from app.db import init_db, get_db, ChatSession, ChatMessage, UserConfig, StatLog, CustomLabel
import json
from collections import Counter
from sqlalchemy import func
from fastapi.responses import StreamingResponse
from google.genai import types
import google.genai as genai
import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation
import io
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
import asyncio
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

def verify_credentials(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    if request.url.path.startswith("/api/v1/admin"):
        expected_username = os.environ.get("API_ADMIN_USERNAME", "admin@email.com")
        expected_password = os.environ.get("API_ADMIN_PASSWORD", "accesstoken")
    else:
        expected_username = os.environ.get("API_USER_USERNAME", "user@email.com")
        expected_password = os.environ.get("API_USER_PASSWORD", "accesstoken")
        
    correct_username = secrets.compare_digest(credentials.username, expected_username)
    correct_password = secrets.compare_digest(credentials.password, expected_password)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="PII Detection API",
    description="API for detecting and anonymizing PII data",
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from any origin (e.g., Next.js dev server or Vercel)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

def get_tier_config_helper(db, user_id):
    user_config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    custom_labels = db.query(CustomLabel).all()
    if user_config:
        tier_config = {"block": set(json.loads(user_config.tier_block)), "redact": set(json.loads(user_config.tier_redact)), "audit": set(json.loads(user_config.tier_audit))}
    else:
        tier_config = {"block": set(TIER_BLOCK), "redact": set(TIER_REDACT), "audit": set(TIER_AUDIT)}
    for cl in custom_labels:
        if cl.tier == "tier_block":
            tier_config["block"].add(cl.name)
        elif cl.tier == "tier_redact":
            tier_config["redact"].add(cl.name)
        elif cl.tier == "tier_audit":
            tier_config["audit"].add(cl.name)
    return tier_config, custom_labels


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    err = traceback.format_exc()
    print("GLOBAL EXCEPTION:", err)
    return JSONResponse(status_code=500, content={"detail": str(exc), "traceback": err})

@app.get("/")
def read_root():
    return {"status": "ok", "message": "PII Detection API is running"}

@app.post("/api/v1/check")
@limiter.limit("20/minute")
async def check_message(request: Request, body: CheckRequest, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    tier_config, custom_labels = get_tier_config_helper(db, body.user_id)
    # 1. Async Pipeline Check
    processed_text, detections, action = await asyncio.to_thread(pipeline.run, body.message, body.allowed_pii, body.ignored_values, tier_config, custom_labels)
    
    # Log stat
    detected_types_list = [d.type for d in detections]
    flagged_sequences_list = [body.message[d.start:d.end] for d in detections]
    stat_log = StatLog(
        user_id=body.user_id,
        session_id=body.session_id,
        action=action,
        detected_types=json.dumps(detected_types_list),
        flagged_sequences=json.dumps(flagged_sequences_list),
        original_message=body.message if action in ["BLOCK", "REDACT"] else None
    )
    db.add(stat_log)
    db.commit()
    
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
        block_set = tier_config["block"] if tier_config else TIER_BLOCK
        blocked_types = [d.type for d in detections if d.type in block_set]
        primary_type = blocked_types[0] if blocked_types else "code"

        # Persist blocked message so it survives session restore
        _session_id = body.session_id
        db_sess = db.query(ChatSession).filter(ChatSession.id == _session_id).first()
        if not db_sess:
            _title = body.message[:30] + "..." if len(body.message) > 30 else body.message
            db_sess = ChatSession(id=_session_id, user_id=body.user_id, title=_title)
            db.add(db_sess)
        blocked_msg = ChatMessage(session_id=_session_id, role="blocked", content=body.message)
        db.add(blocked_msg)
        db.commit()
        
        blocked_redacted_types = [rt for rt in redacted_types_dicts if rt["type"] in block_set]

        raise HTTPException(
            status_code=400,
            detail=BlockResponse(
                action="BLOCK",
                warning=get_block_warning(primary_type),
                blocked_types=[RedactedType(**rt) for rt in blocked_redacted_types]
            ).model_dump()
        )

    # 2. Database & LLM Integration
    session_id = body.session_id
    db_session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not db_session:
        title = body.message[:30] + "..." if len(body.message) > 30 else body.message
        db_session = ChatSession(id=session_id, user_id=body.user_id, title=title)
        db.add(db_session)
        db.commit()

    user_msg = ChatMessage(
        session_id=session_id, 
        role="user", 
        content=processed_text,
        redacted_types=json.dumps(redacted_types_dicts)
    )
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
                
                system_prompt = (
                    "You are a helpful AI assistant. If you receive a message containing redacted information tags (like [TAX_ID], [PERSON], [EMAIL], etc.), you MUST explicitly acknowledge in your reply that the user's sensitive information was safely redacted for privacy, and provide your best answer based on the context.\n\n"
                    "CRITICAL WRITING STYLE GUIDELINES (HUMANIZE YOUR TONE):\n"
                    "1. Avoid AI Vocabulary: Never use words like delve, crucial, testament, underscore, landscape, tapestry, vibrant, pivotal, foster, or intricate.\n"
                    "2. Avoid Sycophancy: Never use servile openers or closers like 'Great question!', 'I hope this helps!', 'You're absolutely right!', or 'Certainly!'. Just answer directly.\n"
                    "3. No Formatting Crutches: Do NOT use em dashes (—), en dashes (–), or emojis. Avoid excessive boldface. Avoid formulaic vertical lists with bolded headers.\n"
                    "4. Natural Rhythm: Vary your sentence lengths. Avoid predictable, robotic cadences. Do not force ideas into groups of three.\n"
                    "5. Direct and Active: Use active voice. Avoid filler phrases ('In order to...', 'Due to the fact...'). Never end with generic upbeat conclusions ('The future looks bright', 'Exciting times lie ahead').\n"
                    "6. Be Direct: Get straight to the point. Avoid rhetorical openers like 'Let's dive in' or 'Here's what you need to know'. Avoid fake-candid phrases like 'Honestly?' or 'Real talk'."
                )
                
                chat = client.aio.chats.create(
                    model="gemini-3.5-flash", 
                    history=gemini_history,
                    config=types.GenerateContentConfig(
                        tools=[{"google_search": {}}],
                        system_instruction=system_prompt
                    )
                )
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

from typing import Union
from app.models import BatchCheckRequest, BatchCheckResponse, CheckResult, BlockResult

@app.post("/api/v1/preview", response_model=Union[CheckResult, BlockResult])
@limiter.limit("30/minute")
async def preview_message(request: Request, body: CheckRequest, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    tier_config, custom_labels = get_tier_config_helper(db, body.user_id)
    processed_text, detections, action = await asyncio.to_thread(pipeline.run, body.message, body.allowed_pii, body.ignored_values, tier_config, custom_labels)
        
    detected_types_list = [d.type for d in detections]
    flagged_sequences_list = [body.message[d.start:d.end] for d in detections]
    stat_log = StatLog(
        user_id=body.user_id,
        session_id=body.session_id,
        action=action,
        detected_types=json.dumps(detected_types_list),
        flagged_sequences=json.dumps(flagged_sequences_list)
    )
    db.add(stat_log)
    db.commit()
        
    redacted_types = [
        RedactedType(type=d.type, subtype=d.subtype, confidence=d.confidence, value=body.message[d.start:d.end])
        for d in detections
    ]
    
    if action == "BLOCK":
        block_set = tier_config["block"] if tier_config else TIER_BLOCK
        blocked_types = [d.type for d in detections if d.type in block_set]
        primary_type = blocked_types[0] if blocked_types else "code"
        
        blocked_redacted_types = [rt for rt in redacted_types if rt.type in block_set]
        
        return BlockResult(
            action="BLOCK",
            warning=get_block_warning(primary_type),
            blocked_types=blocked_redacted_types
        )
    
    return CheckResult(
        action=action,
        was_redacted=(action == "REDACT"),
        message=processed_text,
        redacted_types=redacted_types
    )
@app.get("/api/v1/sessions", response_model=SessionListResponse)
def get_sessions(db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    sessions = db.query(ChatSession).order_by(ChatSession.created_at.desc()).all()
    return SessionListResponse(
        sessions=[ChatSessionInfo(id=s.id, title=s.title, created_at=s.created_at) for s in sessions]
    )

@app.get("/api/v1/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    

    msg_infos = []
    for m in messages:
        rt = []
        if m.redacted_types:
            try:
                rt = json.loads(m.redacted_types)
            except: pass
        msg_infos.append(ChatMessageInfo(role=m.role, content=m.content, created_at=m.created_at, redacted_types=rt))
        
    return SessionDetailResponse(
        id=session.id,
        title=session.title,
        messages=msg_infos
    )

@app.delete("/api/v1/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return {"status": "deleted"}

from pydantic import BaseModel as _BaseModel

class BlockedMessageSave(_BaseModel):
    session_id: str
    message: str
    user_id: str = "default_user"
    model_explanation: Optional[str] = None

@app.post("/api/v1/sessions/save-blocked")
def save_blocked_message(body: BlockedMessageSave, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    """Save a blocked message to the DB so it appears when the session is restored."""
    db_sess = db.query(ChatSession).filter(ChatSession.id == body.session_id).first()
    if not db_sess:
        title = body.message[:30] + "..." if len(body.message) > 30 else body.message
        db_sess = ChatSession(id=body.session_id, title=title)
        db.add(db_sess)
        db.commit()
    blocked_msg = ChatMessage(session_id=body.session_id, role="blocked", content=body.message)
    db.add(blocked_msg)
    if body.model_explanation:
        model_msg = ChatMessage(session_id=body.session_id, role="model", content=body.model_explanation)
        db.add(model_msg)
    db.commit()
    return {"status": "saved"}

from app.models import BatchCheckRequest, BatchCheckResponse, CheckResult, BlockResult

@app.post("/api/v1/check_batch", response_model=BatchCheckResponse)
@limiter.limit("10/minute")
def check_message_batch(request: Request, body: BatchCheckRequest, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    tier_config, custom_labels = get_tier_config_helper(db, body.user_id)

    results = []
    for msg in body.messages:
        processed_text, detections, action = pipeline.run(msg, body.allowed_pii, [], tier_config, custom_labels)
        
        detected_types_list = [d.type for d in detections]
        flagged_sequences_list = [msg[d.start:d.end] for d in detections]
        stat_log = StatLog(
            user_id=body.user_id,
            session_id="batch",
            action=action,
            detected_types=json.dumps(detected_types_list),
            flagged_sequences=json.dumps(flagged_sequences_list),
            original_message=msg if action in ["BLOCK", "REDACT"] else None
        )
        db.add(stat_log)
        db.commit()
        
        redacted_types = [
            RedactedType(type=d.type, subtype=d.subtype, confidence=d.confidence)
            for d in detections
        ]
        
        if action == "BLOCK":
            block_set = tier_config["block"] if tier_config else TIER_BLOCK
            blocked_types = [d.type for d in detections if d.type in block_set]
            primary_type = blocked_types[0] if blocked_types else "code"
            
            blocked_redacted_types = [rt for rt in redacted_types if rt.type in block_set]
            
            results.append(BlockResult(
                action="BLOCK",
                warning=get_block_warning(primary_type),
                blocked_types=blocked_redacted_types
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

@app.get("/api/v1/admin/config/{user_id}", response_model=TierConfigResponse)
def get_user_config(user_id: str, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):

    user_config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not user_config:
        return TierConfigResponse(
            user_id=user_id,
            tier_block=list(TIER_BLOCK),
            tier_redact=list(TIER_REDACT),
            tier_audit=list(TIER_AUDIT)
        )
    return TierConfigResponse(
        user_id=user_id,
        tier_block=json.loads(user_config.tier_block),
        tier_redact=json.loads(user_config.tier_redact),
        tier_audit=json.loads(user_config.tier_audit)
    )

@app.post("/api/v1/admin/config/{user_id}")
def update_user_config(user_id: str, body: TierConfigUpdate, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):

    user_config = db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
    if not user_config:
        user_config = UserConfig(user_id=user_id)
        db.add(user_config)
    
    user_config.tier_block = json.dumps(body.tier_block)
    user_config.tier_redact = json.dumps(body.tier_redact)
    user_config.tier_audit = json.dumps(body.tier_audit)
    db.commit()
    return {"status": "updated"}

from typing import Optional
from datetime import datetime

def fetch_stats(db, user_id=None, start_time=None, end_time=None):
    query = db.query(StatLog)
    if user_id:
        query = query.filter(StatLog.user_id == user_id)
    if start_time:
        query = query.filter(StatLog.created_at >= start_time)
    if end_time:
        query = query.filter(StatLog.created_at <= end_time)
    total = query.with_entities(func.count(StatLog.id)).scalar() or 0
    actions = query.with_entities(StatLog.action, func.count(StatLog.id)).group_by(StatLog.action).all()
    type_counts = Counter()
    seq_counts = Counter()
    for log in query.with_entities(StatLog.detected_types, StatLog.flagged_sequences).all():
        types_val = log[0]
        if isinstance(types_val, str):
            try:
                types_val = json.loads(types_val)
            except:
                types_val = []
        if isinstance(types_val, list):
            type_counts.update(types_val)
            
        seq_val = log[1]
        if seq_val:
            if isinstance(seq_val, str):
                try:
                    seq_val = json.loads(seq_val)
                except:
                    seq_val = []
            if isinstance(seq_val, list):
                seq_counts.update(seq_val)
    return StatsResponse(
        total_requests=total,
        actions=[StatCount(name=a[0], count=a[1]) for a in actions],
        detected_types=[StatCount(name=k, count=v) for k, v in type_counts.items()],
        top_sequences=[StatCount(name=k, count=v) for k, v in seq_counts.most_common(10)]
    )

@app.get("/api/v1/admin/stats", response_model=StatsResponse)
def get_global_stats(start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    return fetch_stats(db, None, start_time, end_time)

@app.get("/api/v1/admin/stats/{user_id}", response_model=StatsResponse)
def get_user_stats(user_id: str, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    return fetch_stats(db, user_id, start_time, end_time)

@app.get("/api/v1/admin/stats/{user_id}", response_model=StatsResponse)
def get_user_stats(user_id: str, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):

    
    base_query = db.query(StatLog).filter(StatLog.user_id == user_id)
    if start_time:
        base_query = base_query.filter(StatLog.created_at >= start_time)
    if end_time:
        base_query = base_query.filter(StatLog.created_at <= end_time)
        
    total = base_query.with_entities(func.count(StatLog.id)).scalar() or 0
    actions = base_query.with_entities(StatLog.action, func.count(StatLog.id)).group_by(StatLog.action).all()
    
    type_counts = Counter()
    seq_counts = Counter()
    for log in base_query.with_entities(StatLog.detected_types, StatLog.flagged_sequences).all():
        types = json.loads(log[0])
        type_counts.update(types)
        if log[1]:
            seqs = json.loads(log[1])
            seq_counts.update(seqs)
            
    top_seqs = seq_counts.most_common(10)
        
    return StatsResponse(
        total_requests=total,
        actions=[StatCount(name=a[0], count=a[1]) for a in actions],
        detected_types=[StatCount(name=k, count=v) for k, v in type_counts.items()],
        top_sequences=[StatCount(name=k, count=v) for k, v in top_seqs]
    )

@app.get("/api/v1/admin/logs/{user_id}")
def get_user_logs(user_id: str, limit: int = 50, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    logs = db.query(StatLog).filter(StatLog.user_id == user_id).order_by(StatLog.created_at.desc()).limit(limit).all()

    result_logs = []
    for log in logs:
        types_val = log.detected_types
        if isinstance(types_val, str):
            try:
                types_val = json.loads(types_val)
            except:
                types_val = []
                
        seq_val = log.flagged_sequences
        if seq_val:
            if isinstance(seq_val, str):
                try:
                    seq_val = json.loads(seq_val)
                except:
                    seq_val = []
        else:
            seq_val = []
            
        result_logs.append({
            "id": log.id,
            "action": log.action,
            "detected_types": types_val,
            "flagged_sequences": seq_val,
            "original_message": log.original_message,
            "created_at": log.created_at.isoformat() + "Z"
        })
    return result_logs


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

from app.models import CustomLabelCreate, CustomLabelResponse
from app.db import CustomLabel

@app.post("/api/v1/admin/custom_labels", response_model=CustomLabelResponse)
def create_custom_label(label: CustomLabelCreate, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):

    existing = db.query(CustomLabel).filter(CustomLabel.name == label.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Label already exists")
    
    dump_data = label.model_dump()
    dump_data["dictionary_words"] = json.dumps(dump_data.get("dictionary_words", []))
    
    # Generate Regex using Gemini (if api key is present)
    api_key = os.getenv("GEMINI_API_KEY", "").strip('"').strip("'")
    if api_key:
        try:
        
        
            client = genai.Client(api_key=api_key)
            words_context = ""
            if label.dictionary_words:
                words_context = f" Examples to match: {', '.join(label.dictionary_words)}."
            prompt = f"Generate ONLY a python regex string to match the PII entity '{label.name}'. Description: '{label.description}'.{words_context} Do not include markdown blocks, slashes, or explanations. Just the raw regex pattern. Make it strict to avoid false positives."
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            dump_data["regex_pattern"] = response.text.strip().strip('`').strip()
        except Exception as e:
            print("Gemini Regex Generation Failed:", e)
    
    db_label = CustomLabel(**dump_data)
    db.add(db_label)
    db.commit()
    db.refresh(db_label)
    
    try:
        words = json.loads(db_label.dictionary_words)
    except:
        words = []
        
    return {
        "id": db_label.id,
        "name": db_label.name,
        "description": db_label.description,
        "tier": db_label.tier,
        "regex_pattern": db_label.regex_pattern,
        "dictionary_words": words,
        "created_at": db_label.created_at
    }

@app.get("/api/v1/admin/custom_labels", response_model=list[CustomLabelResponse])
def get_custom_labels(db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):

    labels = db.query(CustomLabel).all()
    results = []
    for lbl in labels:
        try:
            words = json.loads(lbl.dictionary_words)
        except:
            words = []
        results.append({
            "id": lbl.id,
            "name": lbl.name,
            "description": lbl.description,
            "tier": lbl.tier,
            "regex_pattern": lbl.regex_pattern,
            "dictionary_words": words,
            "created_at": lbl.created_at
        })
    return results

@app.delete("/api/v1/admin/custom_labels/{label_id}")
def delete_custom_label(label_id: int, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):
    db_label = db.query(CustomLabel).filter(CustomLabel.id == label_id).first()
    if not db_label:
        raise HTTPException(status_code=404, detail="Label not found")
    db.delete(db_label)
    db.commit()
    return {"status": "deleted"}

from pydantic import BaseModel
class CustomLabelUpdate(BaseModel):
    dictionary_words: list[str]

@app.put("/api/v1/admin/custom_labels/{label_id}", response_model=CustomLabelResponse)
def update_custom_label(label_id: int, update: CustomLabelUpdate, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):

    db_label = db.query(CustomLabel).filter(CustomLabel.id == label_id).first()
    if not db_label:
        raise HTTPException(status_code=404, detail="Label not found")
        
    db_label.dictionary_words = json.dumps(update.dictionary_words)
    db.commit()
    db.refresh(db_label)
    
    try:
        words = json.loads(db_label.dictionary_words)
    except:
        words = []
        
    return {
        "id": db_label.id,
        "name": db_label.name,
        "description": db_label.description,
        "tier": db_label.tier,
        "regex_pattern": db_label.regex_pattern,
        "dictionary_words": words,
        "created_at": db_label.created_at
    }

from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
import csv
import io

@app.get("/api/v1/admin/custom_labels/xlsx")
def export_custom_labels_xlsx(db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):



    
    labels = db.query(CustomLabel).all()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Entity Labels"
    
    headers = ["Name", "Description", "Tier"]
    ws.append(headers)
    
    for lbl in labels:
        ws.append([lbl.name, lbl.description, lbl.tier])
        
    dv = DataValidation(type="list", formula1='"tier_block,tier_redact,tier_audit"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add('C2:C1000')
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=entity_labels.xlsx"}
    )

@app.get("/api/v1/admin/dictionary/xlsx")
def export_dictionary_xlsx(db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):




    
    labels = db.query(CustomLabel).all()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Dictionary Labels"
    
    headers = ["Name", "Description", "Tier", "Dictionary Words"]
    ws.append(headers)
    
    for lbl in labels:
        try:
            words = json.loads(lbl.dictionary_words)
        except:
            words = []
        ws.append([lbl.name, lbl.description, lbl.tier, ", ".join(words)])
        
    dv = DataValidation(type="list", formula1='"tier_block,tier_redact,tier_audit"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add('C2:C1000')
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=dictionary_labels.xlsx"}
    )

@app.post("/api/v1/admin/custom_labels/import/preview")
async def import_custom_labels_xlsx_preview(file: UploadFile = File(...), db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):


    import os



    from pydantic import BaseModel
    
    class TierResponse(BaseModel):
        tier: str
        
    content = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active
    
    rows = list(ws.rows)
    if not rows:
        raise HTTPException(status_code=400, detail="Empty Excel file.")
        
    header = [cell.value for cell in rows[0]]
    if "Name" not in header:
        raise HTTPException(status_code=400, detail="Invalid Excel format. Missing 'Name' header.")
        
    api_key = os.getenv("GEMINI_API_KEY", "").strip('"').strip("'")
    client = genai.Client(api_key=api_key) if api_key else None
    
    results = []
    
    for row in rows[1:]:
        row_values = [cell.value for cell in row]
        if not row_values or not row_values[0]:
            continue
            
        name = str(row_values[0]).strip()
        description = str(row_values[1]).strip() if len(row_values) > 1 and row_values[1] else ""
        tier = str(row_values[2]).strip() if len(row_values) > 2 and row_values[2] else ""
        words_str = str(row_values[3]).strip() if len(row_values) > 3 and row_values[3] else ""
        
        words = [w.strip() for w in words_str.split(",")] if words_str else []
        
        # Determine if it's new
        existing = db.query(CustomLabel).filter(CustomLabel.name == name).first()
        is_new = existing is None
        
        # If tier is missing, use Gemini to strictly predict it
        if not tier or tier not in ["tier_block", "tier_redact", "tier_audit"]:
            if client:
                try:
                    prompt = f"Assign a tier for the PII entity '{name}'. Description: '{description}'. You MUST choose one of: tier_block, tier_redact, tier_audit."
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=TierResponse,
                            temperature=0.0
                        )
                    )
                    tier_data = json.loads(response.text)
                    tier = tier_data.get("tier", "tier_audit")
                    if tier not in ["tier_block", "tier_redact", "tier_audit"]:
                        tier = "tier_audit"
                except Exception as e:
                    print("Gemini Tier Prediction Failed:", e)
                    tier = "tier_audit"
            else:
                tier = "tier_audit"
                
        results.append({
            "name": name,
            "description": description,
            "tier": tier,
            "dictionary_words": words,
            "is_new": is_new
        })
        
    return {"preview": results}

class ImportConfirmPayload(BaseModel):
    items: list[dict]

@app.post("/api/v1/admin/custom_labels/import/confirm")
def import_custom_labels_xlsx_confirm(payload: ImportConfirmPayload, db: Session = Depends(get_db), credentials: HTTPBasicCredentials = Depends(verify_credentials)):

    import os


    
    api_key = os.getenv("GEMINI_API_KEY", "").strip('"').strip("'")
    client = genai.Client(api_key=api_key) if api_key else None
    
    imported_count = 0
    for item in payload.items:
        name = item.get("name")
        description = item.get("description", "")
        tier = item.get("tier", "tier_audit")
        words = item.get("dictionary_words", [])
        
        existing = db.query(CustomLabel).filter(CustomLabel.name == name).first()
        if existing:
            existing.description = description
            existing.tier = tier
            existing.dictionary_words = json.dumps(words)
        else:
            regex_pattern = ""
            if not words and client:
                try:
                    prompt = f"Generate ONLY a python regex string to match the PII entity '{name}'. Description: '{description}'. Do not include markdown blocks, slashes, or explanations. Just the raw regex pattern."
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                    )
                    regex_pattern = response.text.strip()
                except Exception as e:
                    print("Gemini Regex Generation Failed:", e)
                    
            db_label = CustomLabel(
                name=name,
                description=description,
                tier=tier,
                dictionary_words=json.dumps(words),
                regex_pattern=regex_pattern
            )
            db.add(db_label)
        imported_count += 1
        
    db.commit()
    return {"status": "success", "imported": imported_count}

from fastapi import Form
from app.pipeline.document_stage import extract_text
import tempfile
import os

@app.post("/api/v1/document/upload", response_model=Union[CheckResult, BlockResult])
@limiter.limit("10/minute")
async def upload_document(
    request: Request, 
    file: UploadFile = File(...), 
    user_id: str = Form("default_user"),
    session_id: str = Form("default_session"),
    db: Session = Depends(get_db), 
    credentials: HTTPBasicCredentials = Depends(verify_credentials)
):
    tier_config, custom_labels = get_tier_config_helper(db, user_id)
    
    # Save the uploaded file temporarily
    suffix = os.path.splitext(file.filename)[1] if file.filename else ".tmp"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        content = await file.read()
        tmp.write(content)
        
    try:
        # Extract text using markitdown
        extracted_text = extract_text(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from document, or document was empty.")
        
    # Process the extracted text using the standard pipeline
    processed_text, detections, action = await asyncio.to_thread(pipeline.run, extracted_text, [], [], tier_config, custom_labels)
    
    detected_types_list = [d.type for d in detections]
    flagged_sequences_list = [extracted_text[d.start:d.end] for d in detections]
    
    stat_log = StatLog(
        user_id=user_id,
        session_id=session_id,
        action=action,
        detected_types=json.dumps(detected_types_list),
        flagged_sequences=json.dumps(flagged_sequences_list)
    )
    db.add(stat_log)
    db.commit()
    
    redacted_types = [
        RedactedType(type=d.type, subtype=d.subtype, confidence=d.confidence, value=extracted_text[d.start:d.end])
        for d in detections
    ]
    
    if action == "BLOCK":
        block_set = tier_config["block"] if tier_config else TIER_BLOCK
        blocked_types = [d.type for d in detections if d.type in block_set]
        primary_type = blocked_types[0] if blocked_types else "code"
        
        blocked_redacted_types = [rt for rt in redacted_types if rt.type in block_set]
        
        return BlockResult(
            action="BLOCK",
            warning=get_block_warning(primary_type),
            blocked_types=blocked_redacted_types
        )
    
    return CheckResult(
        action=action,
        was_redacted=(action == "REDACT"),
        message=processed_text,
        redacted_types=redacted_types
    )

