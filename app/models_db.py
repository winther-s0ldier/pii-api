from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB, BIGINT
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.compiler import compiles
import uuid
from sqlalchemy.types import TypeDecorator, CHAR

class UUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def __init__(self, as_uuid=False, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import VARCHAR
            return dialect.type_descriptor(VARCHAR(255))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % uuid.UUID(value).int
            else:
                return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return value

@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(BIGINT, 'sqlite')
def compile_bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"

Base = declarative_base()

class Organization (Base ):
    __tablename__ ="organizations"

    id =Column (UUID (as_uuid =True ),primary_key =True ,default =uuid .uuid4 )
    name =Column (String (255 ),nullable =False )
    is_active =Column (Boolean ,nullable =False ,default =True )
    default_tier_block =Column (JSONB ,nullable =False ,default =list )
    default_tier_redact =Column (JSONB ,nullable =False ,default =list )
    default_tier_audit =Column (JSONB ,nullable =False ,default =list )
    allowed_models =Column (JSONB ,nullable =False ,default =list )
    default_model =Column (String (100 ))
    llm_config =Column (JSONB )
    webhook_url =Column (String (500 ))
    webhook_secret =Column (String (100 ))
    monthly_token_budget =Column (Integer )
    rate_limit_per_user_per_day =Column (Integer )
    retention_days =Column (Integer ,nullable =False ,default =90 )
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())

    users =relationship ("User",back_populates ="org")

class User (Base ):
    __tablename__ ="users"

    __table_args__ =(
    Index ('ix_users_email','email'),
    Index ('ix_users_employee_id','employee_id'),
    Index ('ix_users_org_id','org_id'),
    Index ('ix_users_active_blocked','is_active','is_blocked'),
    )

    id =Column (UUID (as_uuid =True ),primary_key =True ,default =uuid .uuid4 )
    org_id =Column (UUID (as_uuid =True ),ForeignKey ("organizations.id",ondelete ="RESTRICT"))  # nullable: solo/base users have no org
    email =Column (String (255 ))
    employee_id =Column (String (255 ))
    password_hash =Column (String (255 ),nullable =False )
    role =Column (String (20 ),nullable =False )
    is_active =Column (Boolean ,nullable =False ,default =True )
    is_blocked =Column (Boolean ,nullable =False ,default =False )
    blocked_at =Column (DateTime (timezone =True ))
    blocked_by =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="SET NULL"))
    blocked_reason =Column (Text )
    can_upload_pdf =Column (Boolean ,nullable =False ,default =False )
    can_upload_image =Column (Boolean ,nullable =False ,default =False )
    can_upload_csv =Column (Boolean ,nullable =False ,default =False )
    can_upload_docx =Column (Boolean ,nullable =False ,default =False )
    tier_block =Column (JSONB )
    tier_redact =Column (JSONB )
    tier_audit =Column (JSONB )
    allowed_models =Column (JSONB )
    rate_limit_per_day =Column (Integer )
    tokens_used_this_month =Column (Integer ,nullable =False ,default =0 )
    last_login =Column (DateTime (timezone =True ))
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())

    org =relationship ("Organization",back_populates ="users")

class Session (Base ):
    __tablename__ ="sessions"

    __table_args__ =(
    Index ('ix_sessions_user_id','user_id'),
    Index ('ix_sessions_org_id','org_id'),
    )

    id =Column (UUID (as_uuid =True ),primary_key =True ,default =uuid .uuid4 )
    user_id =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="CASCADE"),nullable =False )
    org_id =Column (UUID (as_uuid =True ),ForeignKey ("organizations.id",ondelete ="CASCADE"),nullable =False )
    title =Column (String (255 ))
    model_used =Column (String (100 ))
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())
    updated_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now (),onupdate =func .now ())

    messages =relationship ("Message",back_populates ="session",cascade ="all, delete-orphan")

class Message (Base ):
    __tablename__ ="messages"

    __table_args__ =(
    Index ('ix_messages_session_id','session_id'),
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    session_id =Column (UUID (as_uuid =True ),ForeignKey ("sessions.id",ondelete ="CASCADE"),nullable =False )
    role =Column (String (20 ),nullable =False )
    content =Column (Text ,nullable =False )
    redacted_types =Column (JSONB )
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())

    session =relationship ("Session",back_populates ="messages")

class StatLog (Base ):
    __tablename__ ="stat_logs"

    __table_args__ =(
    Index ('ix_stat_logs_user_id','user_id'),
    Index ('ix_stat_logs_org_id','org_id'),
    Index ('ix_stat_logs_session_id','session_id'),
    Index ('ix_stat_logs_created_at','created_at'),
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    user_id =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="RESTRICT"),nullable =False )
    org_id =Column (UUID (as_uuid =True ),ForeignKey ("organizations.id",ondelete ="RESTRICT"),nullable =False )
    session_id =Column (UUID (as_uuid =True ))
    api_key_id =Column (UUID (as_uuid =True ),ForeignKey ("api_keys.id",ondelete ="SET NULL"))
    action =Column (String (20 ),nullable =False )
    detected_types =Column (JSONB )
    flagged_sequences =Column (JSONB )
    original_message =Column (Text )
    tokens =Column (Integer )
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())

class CustomLabel (Base ):
    __tablename__ ="custom_labels"

    id =Column (Integer ,primary_key =True ,autoincrement =True )
    scope =Column (String (10 ),nullable =False )
    org_id =Column (UUID (as_uuid =True ),ForeignKey ("organizations.id",ondelete ="CASCADE"))
    user_id =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="CASCADE"))
    name =Column (String (100 ),nullable =False )
    description =Column (Text )
    tier =Column (String (20 ),nullable =False )
    regex_pattern =Column (Text )
    dictionary_words =Column (JSONB ,nullable =False ,default =list )
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())

class ApiKey (Base ):
    __tablename__ ="api_keys"

    __table_args__ =(
    Index ('ix_api_keys_key_hash','key_hash'),
    Index ('ix_api_keys_user_id','user_id'),
    Index ('ix_api_keys_org_id','org_id'),
    )

    id =Column (UUID (as_uuid =True ),primary_key =True ,default =uuid .uuid4 )
    user_id =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="CASCADE"),nullable =False )
    org_id =Column (UUID (as_uuid =True ),ForeignKey ("organizations.id",ondelete ="CASCADE"))
    name =Column (String (100 ),nullable =False )
    prefix =Column (String (16 ),nullable =False )
    key_hash =Column (String (64 ),nullable =False ,unique =True )
    scopes =Column (JSONB ,nullable =False ,default =list )
    rate_limit_per_min =Column (Integer ,nullable =False ,default =60 )
    last_used_at =Column (DateTime (timezone =True ))
    last_used_ip =Column (String (45 ))
    expires_at =Column (DateTime (timezone =True ))
    is_active =Column (Boolean ,nullable =False ,default =True )
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())

class Invitation (Base ):
    __tablename__ ="invitations"

    id =Column (UUID (as_uuid =True ),primary_key =True ,default =uuid .uuid4 )
    org_id =Column (UUID (as_uuid =True ),ForeignKey ("organizations.id",ondelete ="CASCADE"),nullable =False )
    invited_by =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="RESTRICT"),nullable =False )
    email =Column (String (255 ))
    employee_id =Column (String (255 ))
    token =Column (String (255 ),nullable =False ,unique =True )
    expires_at =Column (DateTime (timezone =True ),nullable =False )
    status =Column (String (20 ),nullable =False ,default ="pending")
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())

class RefreshToken (Base ):
    __tablename__ ="refresh_tokens"

    id =Column (UUID (as_uuid =True ),primary_key =True ,default =uuid .uuid4 )
    user_id =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="CASCADE"),nullable =False )
    token =Column (String (255 ),nullable =False ,unique =True )
    expires_at =Column (DateTime (timezone =True ),nullable =False )
    revoked =Column (Boolean ,nullable =False ,default =False )
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())

class UserBlockLog (Base ):
    __tablename__ ="user_block_logs"

    id =Column (Integer ,primary_key =True ,autoincrement =True )
    user_id =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="RESTRICT"),nullable =False )
    admin_id =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="RESTRICT"),nullable =False )
    action =Column (String (10 ),nullable =False )
    reason =Column (Text )
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())

class AdminAuditLog (Base ):
    __tablename__ ="admin_audit_log"

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    admin_id =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="RESTRICT"),nullable =False )
    target_user_id =Column (UUID (as_uuid =True ),ForeignKey ("users.id",ondelete ="SET NULL"))
    org_id =Column (UUID (as_uuid =True ),ForeignKey ("organizations.id",ondelete ="RESTRICT"),nullable =False )
    action =Column (String (100 ),nullable =False )
    field_changed =Column (String (100 ))
    old_value =Column (Text )
    created_at =Column (DateTime (timezone =True ),nullable =False ,server_default =func .now ())

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./pi-api.db")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

