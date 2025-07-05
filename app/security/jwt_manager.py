# app/security/jwt_manager.py
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import secrets
from typing import Optional, Dict
from sqlalchemy.orm import Session
from app import models
from app.config import settings
import redis

# Redis for token blacklist
redis_client = redis.from_url(settings.redis_url) if settings.redis_url else None

class JWTManager:
    def __init__(self):
        self.secret_key = settings.secret_key
        self.algorithm = settings.algorithm
        self.access_expire = settings.access_token_expire_minutes
        self.refresh_expire = settings.refresh_token_expire_days
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_expire)
        
        # Enhanced token payload
        to_encode.update({
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": secrets.token_urlsafe(16),  # JWT ID for revocation
            "type": "access",
            "ip": data.get("ip_address"),  # Track IP
            "user_agent": data.get("user_agent")  # Track device
        })
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def create_refresh_token(self, user_id: int, device_id: Optional[str] = None):
        expire = datetime.now(timezone.utc) + timedelta(days=self.refresh_expire)
        jti = secrets.token_urlsafe(16)
        
        to_encode = {
            "user_id": user_id,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": jti,
            "type": "refresh",
            "device_id": device_id or secrets.token_urlsafe(8)
        }
        
        token = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        # Store refresh token in database for tracking
        return token, jti
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Token type verification
            if payload.get("type") != token_type:
                return None
            
            # Check if token is revoked
            jti = payload.get("jti")
            if jti and self.is_token_revoked(jti):
                return None
            
            return payload
            
        except JWTError:
            return None
    
    def revoke_token(self, jti: str, exp: int):
        """Revoke token by adding to blacklist"""
        if redis_client:
            # Store in Redis with expiration
            ttl = exp - int(datetime.now(timezone.utc).timestamp())
            if ttl > 0:
                redis_client.setex(f"revoked_token:{jti}", ttl, "1")
        else:
            # Fallback to database
            # You'd implement database storage here
            pass
    
    def is_token_revoked(self, jti: str) -> bool:
        """Check if token is revoked"""
        if redis_client:
            return redis_client.exists(f"revoked_token:{jti}")
        # Fallback to database check
        return False
    
    def revoke_all_user_tokens(self, user_id: int, db: Session):
        """Revoke all tokens for a user (e.g., password change)"""
        # Implementation would track all active JTIs per user
        pass

# Updated oauth2.py functions
from fastapi import Request
from app.security.jwt_manager import JWTManager

jwt_manager = JWTManager()

def create_tokens(user_id: int, request: Request, db: Session):
    """Create both access and refresh tokens"""
    # Get request info for security
    token_data = {
        "user_id": user_id,
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent")
    }
    
    access_token = jwt_manager.create_access_token(token_data)
    refresh_token, refresh_jti = jwt_manager.create_refresh_token(user_id)
    
    # Store refresh token in database
    refresh_record = models.RefreshToken(
        user_id=user_id,
        jti=refresh_jti,
        expires_at=datetime.now(timezone.utc) + timedelta(days=jwt_manager.refresh_expire),
        ip_address=token_data.get("ip_address"),
        user_agent=token_data.get("user_agent")
    )
    db.add(refresh_record)
    db.commit()
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }