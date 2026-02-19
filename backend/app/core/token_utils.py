from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import TokenBlacklist, UserSession

def create_access_token(
    data: dict, 
    expires_delta: Optional[timedelta] = None,
    db: Optional[Session] = None
) -> str:
    """
    Create a JWT access token and store the session.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "type": "access",
        "jti": str(uuid.uuid4())  # Unique identifier for the token
    })
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    
    # Store the session in the database
    if db and "sub" in data:
        session = UserSession(
            user_id=data["sub"],
            token_jti=to_encode["jti"],
            expires_at=expire,
            user_agent="",  # You can extract this from request headers
            ip_address=""    # You can extract this from request
        )
        db.add(session)
        db.commit()
    
    return encoded_jwt

def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a refresh token.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid.uuid4())
    })
    
    return jwt.encode(
        to_encode,
        settings.REFRESH_SECRET_KEY or settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

def revoke_token(token: str, db: Session) -> None:
    """
    Add a token to the blacklist.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False}
        )
        
        # Add to blacklist if it has an expiration
        if "exp" in payload:
            expire = datetime.utcfromtimestamp(payload["exp"])
            now = datetime.utcnow()
            
            if expire > now:  # Only add if not already expired
                db_token = TokenBlacklist(
                    jti=payload.get("jti", str(uuid.uuid4())),
                    token=token,
                    expires_at=expire
                )
                db.add(db_token)
                db.commit()
                
                # Invalidate user session
                if "jti" in payload:
                    db.query(UserSession).filter(
                        UserSession.token_jti == payload["jti"]
                    ).update({"revoked": True})
                    db.commit()
                    
    except JWTError:
        pass  # Token is invalid, nothing to revoke
