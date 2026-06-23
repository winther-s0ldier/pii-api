from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import os
import logging
from dotenv import load_dotenv
load_dotenv(override=True)

logger = logging.getLogger(__name__)

from app.models import (
    CheckRequest, CheckResponse, BlockResponse, RedactedType,
    SessionListResponse, SessionDetailResponse, ChatSessionInfo, ChatMessageInfo,
    TierConfigUpdate, TierConfigResponse, StatsResponse, StatCount
)
from app.pipeline import pipeline
from app.pipeline import regex_stage
from app.config import get_block_warning, TIER_BLOCK, TIER_REDACT, TIER_AUDIT
from app.models_db import init_db, get_db, Session as ChatSession, Message as ChatMessage, User, StatLog, CustomLabel, Organization
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
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient

security_bearer = HTTPBearer(auto_error=False)


CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "https://rapid-hyena-22.clerk.accounts.dev/.well-known/jwks.json")
try:
    jwks_client = PyJWKClient(CLERK_JWKS_URL, cache_keys=True, lifespan=3600)
except:
    jwks_client = None

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip('"').strip("'")
_gemini_client = genai.Client(api_key=_GEMINI_API_KEY) if _GEMINI_API_KEY else None


def verify_credentials(request: Request, bearer_creds: HTTPAuthorizationCredentials = Depends(security_bearer), db: Session = Depends(get_db)):
    from app.models_db import Organization, User
    try:
        user = None

        # Clerk JWT validation
        global jwks_client
        if not jwks_client:
            try:
                jwks_client = PyJWKClient(CLERK_JWKS_URL, cache_keys=True, lifespan=3600)
            except Exception as e:
                print("Failed to initialize JWKS client:", e)


        if not user and bearer_creds and jwks_client:
            token = bearer_creds.credentials
            try:
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                data = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    options={"verify_aud": False},
                    leeway=600
                )
                import uuid
                clerk_id = data.get("sub")
                clerk_org_id = data.get("org_id")
                
                if clerk_org_id:
                    # Deterministic UUID5 for zero-schema organization syncing
                    CLERK_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, 'clerk.adopshun.com')
                    org_uuid = uuid.uuid5(CLERK_NAMESPACE, clerk_org_id)
                    org = db.query(Organization).filter(Organization.id == org_uuid).first()
                    if not org:
                        org_slug = data.get("org_slug", "Unknown Organization")
                        org = Organization(
                            id=org_uuid,
                            name=org_slug.replace("-", " ").title() if org_slug else "New Organization",
                            is_active=True
                        )
                        db.add(org)
                else:
                    org = None

                user = db.query(User).filter(User.email == clerk_id).first()
                if not user:
                    user = User(
                        org_id=org.id if org else None,
                        email=clerk_id,
                        role="admin" if data.get("org_role") == "org:admin" or not clerk_org_id else "employee",
                        password_hash="clerk_managed",
                        is_active=True,
                        rate_limit_per_day=15 if not clerk_org_id else None
                    )
                    db.add(user)
                    db.commit()
                    db.refresh(user)
                else:
                    if clerk_org_id and org and user.org_id != org.id:
                        user.org_id = org.id
                        user.role = "admin" if data.get("org_role") == "org:admin" else "employee"
                        user.rate_limit_per_day = None
                    db.commit()
                user.is_base_user = (clerk_org_id is None)
                request.state.clerk_org_id = clerk_org_id
                request.state.clerk_user_id = clerk_id
                if getattr(user, 'is_blocked', False):
                    raise HTTPException(status_code=403, detail="Account suspended")
            except HTTPException:
                raise
            except Exception as e:
                logger.error("Clerk JWT Decode Error: %s", e, exc_info=True)
                raise HTTPException(status_code=401, detail=f"Invalid Clerk Token: {str(e)}")
                
        if not user:
            print("Auth Failed: User not found or bearer token missing.")
            if not bearer_creds:
                print("- No Bearer token provided in headers")
            raise HTTPException(
                status_code=401,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        request.state.is_base_user = getattr(user, 'is_base_user', True)
            
        if request.url.path.startswith("/api/v1/admin") and user.role not in ["admin", "super_admin"]:
            raise HTTPException(
                status_code=403,
                detail="Admin privileges required"
            )
        request.state.current_user = user
        return True
    finally:
        pass

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="PII Detection API",
    description="API for detecting and anonymizing PII data",
)

from fastapi.middleware.cors import CORSMiddleware

_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,https://pii-api-mu.vercel.app").split(",")
if "https://chat.adopshun.com" not in _origins:
    _origins.append("https://chat.adopshun.com")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

def get_tier_config_helper(db, user):
    is_base = getattr(user, "is_base_user", True)
    if user:
        if is_base:
            custom_labels = db.query(CustomLabel).filter(CustomLabel.user_id == user.id).all()
        else:
            custom_labels = db.query(CustomLabel).filter(CustomLabel.org_id == user.org_id).all()
    else:
        custom_labels = []
        
    if user and user.tier_block:
        tier_config = {"block": set(user.tier_block), "redact": set(user.tier_redact), "audit": set(user.tier_audit)}
    else:
        if user and not is_base:
            org = db.query(Organization).filter(Organization.id == user.org_id).first()
            if org and org.default_tier_block:
                tier_config = {
                    "block": set(org.default_tier_block),
                    "redact": set(org.default_tier_redact),
                    "audit": set(org.default_tier_audit)
                }
                for cl in custom_labels:
                    if cl.tier == "tier_block":
                        tier_config["block"].add(cl.name)
                    elif cl.tier == "tier_redact":
                        tier_config["redact"].add(cl.name)
                    elif cl.tier == "tier_audit":
                        tier_config["audit"].add(cl.name)
                return tier_config, custom_labels
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
    response = JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    origin = request.headers.get("origin")
    allowed_origins = set(os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","))
    allowed_origins.add("https://chat.adopshun.com")
    if origin and origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

@app.get("/")
def read_root():
    return {"status": "ok", "message": "PII Detection API is running"}

@app.post("/api/v1/check")
@limiter.limit("20/minute")
async def check_message(request: Request, body: CheckRequest, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    user = request.state.current_user
    tier_config, custom_labels = get_tier_config_helper(db, user)
    # 1. Async Pipeline Check
    processed_text, detections, action = await asyncio.to_thread(pipeline.run, body.message, body.allowed_pii, body.ignored_values, tier_config, custom_labels)
    
    import uuid
    try:
        real_sess_id = uuid.UUID(body.session_id)
    except:
        real_sess_id = None

    # Log stat
    detected_types_list = [d.type for d in detections]
    flagged_sequences_list = [body.message[d.start:d.end] for d in detections]
    stat_log = StatLog(
        user_id=user.id,
        org_id=user.org_id,
        session_id=real_sess_id,
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
        if real_sess_id:
            db_sess = db.query(ChatSession).filter(ChatSession.id == real_sess_id).first()
            if not db_sess:
                _title = body.message[:30] + "..." if len(body.message) > 30 else body.message
                db_sess = ChatSession(id=real_sess_id, user_id=user.id, org_id=user.org_id, title=_title)
                db.add(db_sess)
            blocked_msg = ChatMessage(session_id=real_sess_id, role="blocked", content=body.message)
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
    if real_sess_id:
        db_session = db.query(ChatSession).filter(ChatSession.id == real_sess_id).first()
        if not db_session:
            title = body.message[:30] + "..." if len(body.message) > 30 else body.message
            db_session = ChatSession(id=real_sess_id, user_id=user.id, org_id=user.org_id, title=title)
            db.add(db_session)
            db.commit()

        user_msg = ChatMessage(
            session_id=real_sess_id, 
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
        if _gemini_client and real_sess_id:
            history = db.query(ChatMessage).filter(ChatMessage.session_id == real_sess_id).order_by(ChatMessage.created_at).all()
            gemini_history = []
            for msg in history[:-1]:
                gemini_history.append({"role": msg.role, "parts": [{"text": msg.content}]})
                
            try:
            
                client = _gemini_client

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
                    model="gemini-3.1-pro-preview",
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
                
                if real_sess_id:
                    model_msg = ChatMessage(session_id=real_sess_id, role="model", content=llm_reply)
                    db.add(model_msg)
                    db.commit()
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'text': f'Error calling Gemini: {str(e)}'})}\n\n"
        else:
            llm_reply = "I am the pseudo LLM. I received your message securely. (Gemini API key not configured)"
            yield f"data: {json.dumps({'type': 'chunk', 'text': llm_reply})}\n\n"
            
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

from typing import Union
from app.models import BatchCheckRequest, BatchCheckResponse, CheckResult, BlockResult

@app.post("/api/v1/preview", response_model=Union[CheckResult, BlockResult])
@limiter.limit("30/minute")
async def preview_message(request: Request, body: CheckRequest, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    user = request.state.current_user
    tier_config, custom_labels = get_tier_config_helper(db, user)
    processed_text, detections, action = await asyncio.to_thread(pipeline.run, body.message, body.allowed_pii, body.ignored_values, tier_config, custom_labels)
        
    import uuid
    try:
        real_sess_id = uuid.UUID(body.session_id)
    except:
        real_sess_id = None

    detected_types_list = [d.type for d in detections]
    flagged_sequences_list = [body.message[d.start:d.end] for d in detections]
    stat_log = StatLog(
        user_id=user.id,
        org_id=user.org_id,
        session_id=real_sess_id,
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
def get_sessions(request: Request, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    user = request.state.current_user
    is_base = getattr(request.state, "is_base_user", True)
    if is_base:
        sessions = db.query(ChatSession).filter(ChatSession.user_id == user.id).order_by(ChatSession.created_at.desc()).all()
    else:
        sessions = db.query(ChatSession).filter(ChatSession.org_id == user.org_id).order_by(ChatSession.created_at.desc()).all()
    return SessionListResponse(
        sessions=[ChatSessionInfo(id=str(s.id), title=s.title, created_at=s.created_at) for s in sessions]
    )

@app.get("/api/v1/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(request: Request, session_id: str, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    user = request.state.current_user
    is_base = getattr(request.state, "is_base_user", True)
    query = db.query(ChatSession).filter(ChatSession.id == session_id)
    if is_base:
        query = query.filter(ChatSession.user_id == user.id)
    else:
        query = query.filter(ChatSession.org_id == user.org_id)
    session = query.first()
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
        id=str(session.id),
        title=session.title,
        messages=msg_infos
    )

@app.delete("/api/v1/sessions/{session_id}")
def delete_session(request: Request, session_id: str, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    user = request.state.current_user
    is_base = getattr(request.state, "is_base_user", True)
    query = db.query(ChatSession).filter(ChatSession.id == session_id)
    if is_base:
        query = query.filter(ChatSession.user_id == user.id)
    else:
        query = query.filter(ChatSession.org_id == user.org_id)
    session = query.first()
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
    blocked_types: Optional[list] = None

@app.post("/api/v1/sessions/save-blocked")
def save_blocked_message(request: Request, body: BlockedMessageSave, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    user = request.state.current_user
    db_sess = db.query(ChatSession).filter(ChatSession.id == body.session_id).first()
    if not db_sess:
        title = body.message[:30] + "..." if len(body.message) > 30 else body.message
        db_sess = ChatSession(id=body.session_id, user_id=user.id, org_id=user.org_id, title=title)
        db.add(db_sess)
        db.commit()
    blocked_msg = ChatMessage(session_id=body.session_id, role="blocked", content=body.message)
    db.add(blocked_msg)
    if body.model_explanation:
        model_msg = ChatMessage(session_id=body.session_id, role="model", content=body.model_explanation)
        db.add(model_msg)
    detected = [t.get("type", "") for t in (body.blocked_types or []) if isinstance(t, dict)]
    flagged = [t.get("value", "") for t in (body.blocked_types or []) if isinstance(t, dict)]
    db.add(StatLog(
        user_id=user.id,
        org_id=user.org_id,
        session_id=body.session_id,
        action="BLOCK",
        detected_types=json.dumps(detected),
        flagged_sequences=json.dumps(flagged),
        original_message=body.message,
    ))
    db.commit()
    return {"status": "saved"}

from app.models import BatchCheckRequest, BatchCheckResponse, CheckResult, BlockResult

@app.post("/api/v1/check_batch", response_model=BatchCheckResponse)
@limiter.limit("10/minute")
async def check_message_batch(request: Request, body: BatchCheckRequest, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    user = request.state.current_user
    tier_config, custom_labels = get_tier_config_helper(db, user)

    pipeline_results = await asyncio.gather(*[
        asyncio.to_thread(pipeline.run, msg, body.allowed_pii, [], tier_config, custom_labels)
        for msg in body.messages
    ])

    block_set = tier_config["block"] if tier_config else TIER_BLOCK
    results = []
    for msg, (processed_text, detections, action) in zip(body.messages, pipeline_results):
        db.add(StatLog(
            user_id=user.id,
            org_id=user.org_id,
            session_id=None,
            action=action,
            detected_types=json.dumps([d.type for d in detections]),
            flagged_sequences=json.dumps([msg[d.start:d.end] for d in detections]),
            original_message=msg if action in ["BLOCK", "REDACT"] else None
        ))
        redacted_types = [
            RedactedType(type=d.type, subtype=d.subtype, confidence=d.confidence)
            for d in detections
        ]
        if action == "BLOCK":
            blocked = [d.type for d in detections if d.type in block_set]
            results.append(BlockResult(
                action="BLOCK",
                warning=get_block_warning(blocked[0] if blocked else "code"),
                blocked_types=[rt for rt in redacted_types if rt.type in block_set]
            ))
        else:
            results.append(CheckResult(
                action=action,
                was_redacted=(action == "REDACT"),
                message=processed_text,
                redacted_types=redacted_types
            ))
    db.commit()
    return BatchCheckResponse(results=results)
@app.get("/api/v1/health")
def health():
    return {"status": "ok"}

def _resolve_org_user(user_id: str, current_user, db) -> "User | None":
    """Return a User in current_user's org by UUID string, username, or email."""
    import uuid as _uuid
    try:
        uid = _uuid.UUID(user_id)
        return db.query(User).filter(User.id == uid, User.org_id == current_user.org_id).first()
    except ValueError:
        return db.query(User).filter(
            (User.username == user_id) | (User.email == user_id),
            User.org_id == current_user.org_id
        ).first()


@app.get("/api/v1/admin/config/{user_id}", response_model=TierConfigResponse)
def get_user_config(request: Request, user_id: str, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    current_user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    
    target_user = None
    if user_id in ["default_user", "me"]:
        if is_base_user:
            target_user = current_user
        else:
            if user_id == "default_user":
                from app.models_db import Organization
                org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
                if not org or not org.default_tier_block:
                    return TierConfigResponse(
                        user_id=user_id,
                        tier_block=list(TIER_BLOCK),
                        tier_redact=list(TIER_REDACT),
                        tier_audit=list(TIER_AUDIT)
                    )
                return TierConfigResponse(
                    user_id=user_id,
                    tier_block=org.default_tier_block,
                    tier_redact=org.default_tier_redact,
                    tier_audit=org.default_tier_audit
                )
            else:
                target_user = current_user
    else:
        if is_base_user:
            target_user = current_user
        else:
            target_user = _resolve_org_user(user_id, current_user, db)
            if not target_user:
                raise HTTPException(status_code=404, detail="User not found")

    if not target_user or not target_user.tier_block:
        return TierConfigResponse(
            user_id=user_id,
            tier_block=list(TIER_BLOCK),
            tier_redact=list(TIER_REDACT),
            tier_audit=list(TIER_AUDIT)
        )
    return TierConfigResponse(
        user_id=user_id,
        tier_block=target_user.tier_block,
        tier_redact=target_user.tier_redact,
        tier_audit=target_user.tier_audit
    )

@app.post("/api/v1/admin/config/{user_id}")
def update_user_config(request: Request, user_id: str, body: TierConfigUpdate, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    current_user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    
    if user_id in ["default_user", "me"]:
        if is_base_user:
            current_user.tier_block = body.tier_block
            current_user.tier_redact = body.tier_redact
            current_user.tier_audit = body.tier_audit
            db.add(current_user)
            db.commit()
            return {"status": "updated"}
        else:
            if user_id == "default_user":
                from app.models_db import Organization
                org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
                if org:
                    org.default_tier_block = body.tier_block
                    org.default_tier_redact = body.tier_redact
                    org.default_tier_audit = body.tier_audit
                    db.add(org)
                    db.commit()
                    return {"status": "updated"}
                raise HTTPException(status_code=404, detail="Organization not found")
            else:
                current_user.tier_block = body.tier_block
                current_user.tier_redact = body.tier_redact
                current_user.tier_audit = body.tier_audit
                db.add(current_user)
                db.commit()
                return {"status": "updated"}
    else:
        if is_base_user:
            target_user = current_user
        else:
            target_user = _resolve_org_user(user_id, current_user, db)
            if not target_user:
                raise HTTPException(status_code=404, detail="User not found")

        target_user.tier_block = body.tier_block
        target_user.tier_redact = body.tier_redact
        target_user.tier_audit = body.tier_audit
        db.add(target_user)
        db.commit()
        return {"status": "updated"}

from typing import Optional
from datetime import datetime

def fetch_stats(db, current_user, is_base_user: bool, user_id=None, start_time=None, end_time=None):
    # ponytail: resolve "me" to the current user's UUID string
    if user_id == "me":
        user_id = str(current_user.id)

    query = db.query(StatLog)
    
    # Isolation
    if is_base_user:
        query = query.filter(StatLog.user_id == current_user.id)
    else:
        query = query.filter(StatLog.org_id == current_user.org_id)
        
    if user_id and user_id not in ["default_user", "me"]:
        if is_base_user:
            query = query.filter(StatLog.user_id == current_user.id)
        else:
            target_user = _resolve_org_user(user_id, current_user, db)
            if not target_user:
                return StatsResponse(total_requests=0, actions=[], detected_types=[], top_sequences=[])
            query = query.filter(StatLog.user_id == target_user.id)
            
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
def get_global_stats(request: Request, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    current_user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    return fetch_stats(db, current_user, is_base_user, None, start_time, end_time)

@app.get("/api/v1/admin/stats/{user_id}", response_model=StatsResponse)
def get_user_stats(request: Request, user_id: str, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    current_user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    return fetch_stats(db, current_user, is_base_user, user_id, start_time, end_time)

@app.get("/api/v1/admin/logs/{user_id}")
def get_user_logs(request: Request, user_id: str, limit: int = 50, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    current_user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    
    # ponytail: handle keyword scopes for base and org users simply
    if is_base_user:
        # Base users are strictly isolated to their own logs
        logs = db.query(StatLog).filter(StatLog.user_id == current_user.id).order_by(StatLog.created_at.desc()).limit(limit).all()
    else:
        # Org users
        if user_id == "me":
            logs = db.query(StatLog).filter(StatLog.user_id == current_user.id).order_by(StatLog.created_at.desc()).limit(limit).all()
        elif user_id == "default_user":
            # Return org-wide logs
            logs = db.query(StatLog).filter(StatLog.org_id == current_user.org_id).order_by(StatLog.created_at.desc()).limit(limit).all()
        else:
            target_user = _resolve_org_user(user_id, current_user, db)
            if not target_user:
                raise HTTPException(status_code=404, detail="User not found")
            logs = db.query(StatLog).filter(StatLog.user_id == target_user.id).order_by(StatLog.created_at.desc()).limit(limit).all()

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
        else:
            seq_val = []
            
        result_logs.append({
            "id": log.id,
            "action": log.action,
            "detected_types": types_val,
            "flagged_sequences": seq_val,
            "original_message": log.original_message,
            "created_at": log.created_at.isoformat()
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

@app.post("/api/v1/admin/custom_labels", response_model=CustomLabelResponse)
def create_custom_label(request: Request, label: CustomLabelCreate, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    user = request.state.current_user if hasattr(request.state, 'current_user') else None
    is_base_user = getattr(request.state, "is_base_user", True)
    
    if is_base_user:
        existing = db.query(CustomLabel).filter(CustomLabel.name == label.name, CustomLabel.user_id == user.id).first()
    else:
        existing = db.query(CustomLabel).filter(CustomLabel.name == label.name, CustomLabel.org_id == user.org_id).first()
        
    if existing:
        raise HTTPException(status_code=400, detail="Label already exists")
    
    dump_data = label.model_dump()
    dump_data["dictionary_words"] = json.dumps(dump_data.get("dictionary_words", []))
    
    if _gemini_client:
        try:
            client = _gemini_client
            words_context = ""
            if label.dictionary_words:
                words_context = f" Examples to match: {', '.join(label.dictionary_words)}."
            prompt = f"Generate ONLY a python regex string to match the PII entity '{label.name}'. Description: '{label.description}'.{words_context} Do not include markdown blocks, slashes, or explanations. Just the raw regex pattern. Make it strict to avoid false positives."
            response = client.models.generate_content(
                model='gemini-3.1-pro-preview',
                contents=prompt,
            )
            dump_data["regex_pattern"] = response.text.strip().strip('`').strip()
        except Exception as e:
            print("Gemini Regex Generation Failed:", e)
            
    db_label = CustomLabel(
        name=dump_data.get("name"),
        description=dump_data.get("description"),
        tier=dump_data.get("tier"),
        regex_pattern=dump_data.get("regex_pattern"),
        scope="user" if is_base_user else "org",
        user_id=user.id if is_base_user else None,
        org_id=None if is_base_user else user.org_id,
        dictionary_words=dump_data.get("dictionary_words", "[]")
    )
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
def get_custom_labels(request: Request, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    current_user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    
    if is_base_user:
        labels = db.query(CustomLabel).filter(CustomLabel.user_id == current_user.id).all()
    else:
        labels = db.query(CustomLabel).filter(CustomLabel.org_id == current_user.org_id).all()
        
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
def delete_custom_label(request: Request, label_id: int, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    
    db_label = db.query(CustomLabel).filter(CustomLabel.id == label_id).first()
    if not db_label:
        raise HTTPException(status_code=404, detail="Label not found")
        
    if is_base_user and db_label.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if not is_base_user and db_label.org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
        
    db.delete(db_label)
    db.commit()
    return {"status": "deleted"}

from pydantic import BaseModel
class CustomLabelUpdate(BaseModel):
    dictionary_words: list[str]

@app.put("/api/v1/admin/custom_labels/{label_id}", response_model=CustomLabelResponse)
def update_custom_label(request: Request, label_id: int, update: CustomLabelUpdate, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    
    db_label = db.query(CustomLabel).filter(CustomLabel.id == label_id).first()
    if not db_label:
        raise HTTPException(status_code=404, detail="Label not found")
        
    if is_base_user and db_label.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if not is_base_user and db_label.org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
        
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
def export_custom_labels_xlsx(request: Request, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    current_user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    
    if is_base_user:
        labels = db.query(CustomLabel).filter(CustomLabel.user_id == current_user.id).all()
    else:
        labels = db.query(CustomLabel).filter(CustomLabel.org_id == current_user.org_id).all()
        
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
def export_dictionary_xlsx(request: Request, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    current_user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    
    if is_base_user:
        labels = db.query(CustomLabel).filter(CustomLabel.user_id == current_user.id).all()
    else:
        labels = db.query(CustomLabel).filter(CustomLabel.org_id == current_user.org_id).all()
        
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
async def import_custom_labels_xlsx_preview(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
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
        
    current_user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    
    client = _gemini_client
    
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
        if is_base_user:
            existing = db.query(CustomLabel).filter(CustomLabel.name == name, CustomLabel.user_id == current_user.id).first()
        else:
            existing = db.query(CustomLabel).filter(CustomLabel.name == name, CustomLabel.org_id == current_user.org_id).first()
        is_new = existing is None
        
        # If tier is missing, use Gemini to strictly predict it
        if not tier or tier not in ["tier_block", "tier_redact", "tier_audit"]:
            if client:
                try:
                    prompt = f"Assign a tier for the PII entity '{name}'. Description: '{description}'. You MUST choose one of: tier_block, tier_redact, tier_audit."
                    response = client.models.generate_content(
                        model='gemini-3.1-pro-preview',
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
def import_custom_labels_xlsx_confirm(request: Request, payload: ImportConfirmPayload, db: Session = Depends(get_db), _: bool = Depends(verify_credentials)):
    import os
    
    current_user = request.state.current_user
    is_base_user = getattr(request.state, "is_base_user", True)
    
    client = _gemini_client
    
    imported_count = 0
    for item in payload.items:
        name = item.get("name")
        description = item.get("description", "")
        tier = item.get("tier", "tier_audit")
        words = item.get("dictionary_words", [])
        
        if is_base_user:
            existing = db.query(CustomLabel).filter(CustomLabel.name == name, CustomLabel.user_id == current_user.id).first()
        else:
            existing = db.query(CustomLabel).filter(CustomLabel.name == name, CustomLabel.org_id == current_user.org_id).first()
            
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
                        model='gemini-3.1-pro-preview',
                        contents=prompt,
                    )
                    regex_pattern = response.text.strip()
                except Exception as e:
                    print("Gemini Regex Generation Failed:", e)
                    
            db_label = CustomLabel(
                name=name,
                description=description,
                tier=tier,
                scope="user" if is_base_user else "org",
                user_id=current_user.id if is_base_user else None,
                org_id=None if is_base_user else current_user.org_id,
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
    session_id: str = Form("default_session"),
    db: Session = Depends(get_db), 
    _: bool = Depends(verify_credentials)
):
    user = request.state.current_user
    tier_config, custom_labels = get_tier_config_helper(db, user)
    
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
    
    import uuid
    try:
        real_sess_id = uuid.UUID(session_id)
    except:
        real_sess_id = None

    detected_types_list = [d.type for d in detections]
    flagged_sequences_list = [extracted_text[d.start:d.end] for d in detections]
    
    stat_log = StatLog(
        user_id=user.id,
        org_id=user.org_id,
        session_id=real_sess_id,
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


@app.post("/api/v1/admin/invite/bulk")
async def bulk_invite(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_credentials),
):
    import csv, io
    from clerk_backend_api import Clerk
    from clerk_backend_api.models import CreateOrganizationInvitationBulkRequestBody

    clerk_org_id = getattr(request.state, "clerk_org_id", None)
    clerk_user_id = getattr(request.state, "clerk_user_id", None)
    if not clerk_org_id:
        raise HTTPException(status_code=400, detail="No active organization in session")

    content = (await file.read()).decode("utf-8-sig")
    reader = csv.reader(io.StringIO(content))
    emails = []
    for i, row in enumerate(reader):
        if not row:
            continue
        val = row[0].strip()
        if i == 0 and ("email" in val.lower() or "@" not in val):
            continue  # skip header row
        if "@" in val:
            emails.append(val.lower())

    if not emails:
        raise HTTPException(status_code=400, detail="No valid email addresses found in CSV")

    clerk = Clerk(bearer_auth=os.getenv("CLERK_SECRET_KEY"))
    sent, failed = [], []

    for i in range(0, len(emails), 10):
        batch = emails[i:i + 10]
        try:
            clerk.organization_invitations.bulk_create(
                organization_id=clerk_org_id,
                request_body=[
                    CreateOrganizationInvitationBulkRequestBody(
                        email_address=email,
                        role="org:member",
                        inviter_user_id=clerk_user_id,
                        redirect_url="https://chat.adopshun.com",
                    )
                    for email in batch
                ],
            )
            sent.extend(batch)
        except Exception as e:
            logger.warning("Bulk invite batch failed: %s", e)
            failed.extend(batch)

    return {"sent": sent, "failed": failed, "total": len(emails)}
