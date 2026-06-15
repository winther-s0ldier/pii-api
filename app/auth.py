import os 
import jwt 
from datetime import datetime ,timedelta 
import bcrypt 
from fastapi import Depends ,HTTPException ,status 
from fastapi .security import OAuth2PasswordBearer 
from sqlalchemy .orm import Session 
from app .db import get_db 
from app .models_db import User 


SECRET_KEY =os .environ .get ("JWT_SECRET","09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
if os .environ .get ("ENV")=="production"and "JWT_SECRET"not in os .environ :
    raise RuntimeError ("JWT_SECRET must be set in production")

ALGORITHM ="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES =60 *24 *7 

oauth2_scheme =OAuth2PasswordBearer (tokenUrl ="api/v1/auth/login")

def verify_password (plain_password ,hashed_password ):
    return bcrypt .checkpw (plain_password .encode ('utf-8'),hashed_password .encode ('utf-8'))

def get_password_hash (password ):
    return bcrypt .hashpw (password .encode ('utf-8'),bcrypt .gensalt ()).decode ('utf-8')

def create_access_token (data :dict ,expires_delta :timedelta |None =None ):
    to_encode =data .copy ()
    if expires_delta :
        expire =datetime .utcnow ()+expires_delta 
    else :
        expire =datetime .utcnow ()+timedelta (minutes =ACCESS_TOKEN_EXPIRE_MINUTES )
    to_encode .update ({"exp":expire })
    encoded_jwt =jwt .encode (to_encode ,SECRET_KEY ,algorithm =ALGORITHM )
    return encoded_jwt 

def get_current_user (token :str =Depends (oauth2_scheme ),db :Session =Depends (get_db )):
    credentials_exception =HTTPException (
    status_code =status .HTTP_401_UNAUTHORIZED ,
    detail ="Could not validate credentials",
    headers ={"WWW-Authenticate":"Bearer"},
    )
    try :
        payload =jwt .decode (token ,SECRET_KEY ,algorithms =[ALGORITHM ])
        user_id :str =payload .get ("sub")
        if user_id is None :
            raise credentials_exception 
    except jwt .PyJWTError :
        raise credentials_exception 

    user =db .query (User ).filter (User .id ==user_id ).first ()
    if user is None or not user .is_active or user .is_blocked :
        raise credentials_exception 
    return user 

def get_current_admin (current_user :User =Depends (get_current_user )):
    if current_user .role not in ["admin","super_admin"]:
        raise HTTPException (status_code =status .HTTP_403_FORBIDDEN ,detail ="Admin privileges required")
    return current_user 
