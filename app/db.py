from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os

from sqlalchemy import event
from sqlalchemy.engine import Engine

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./chat.db")
is_sqlite = DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
if is_sqlite:
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
else:
    engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True, pool_recycle=300)

if is_sqlite:
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ChatSession(Base):
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=True)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    role = Column(String)
    content = Column(Text)
    redacted_types = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    session = relationship("ChatSession", back_populates="messages")

class UserConfig(Base):
    __tablename__ = "user_configs"
    
    user_id = Column(String, primary_key=True, index=True)
    tier_block = Column(Text, default="[]")
    tier_redact = Column(Text, default="[]")
    tier_audit = Column(Text, default="[]")

class StatLog(Base):
    __tablename__ = "stat_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    org_id = Column(String, default="d30833ed-5595-48df-8be1-45988855c831")
    session_id = Column(String)
    action = Column(String)
    detected_types = Column(Text)
    flagged_sequences = Column(Text, default="[]")
    original_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class CustomLabel(Base):
    __tablename__ = "custom_labels"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text)
    tier = Column(String)
    regex_pattern = Column(String, nullable=True)
    dictionary_words = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
