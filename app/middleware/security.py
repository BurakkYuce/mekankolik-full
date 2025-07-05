# app/middleware/security.py
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import time
import logging
from datetime import datetime
from typing import Optional
import re
from app.config import settings

# Security logger setup
security_logger = logging.getLogger('security')
security_handler = logging.FileHandler('security.log')
security_handler.setFormatter(
    logging.Formatter('%(asctime)s - SECURITY - %(levelname)s - %(message)s')
)
security_logger.addHandler(security_handler)
security_logger.setLevel(logging.WARNING)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add comprehensive security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # HSTS for production
        if settings.is_production():
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # CSP header
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self'",
            "connect-src 'self'",
            "frame-ancestors 'none'"
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # Remove server header
         # With this fix:
        if "server" in response.headers:
            del response.headers["server"]
        
        return response

class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Validate and sanitize incoming requests"""
    
    MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB max
    SUSPICIOUS_PATTERNS = [
        r"(\%27)|(\')|(\%2527)",  # SQL injection
        r"((\%3C)|<)((\%2F)|\/)*[a-z0-9\%]+((\%3E)|>)",  # XSS
        r"(\%22)|(\")|(\.\.\/)",  # Path traversal
        r"(;|--|\/\*|\*\/|@@|@)",  # SQL comments
        r"union.*select",  # SQL union
        r"<script.*?>.*?</script>",  # Script tags
    ]
    
    async def dispatch(self, request: Request, call_next):
        # Check request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_REQUEST_SIZE:
            security_logger.warning(
                f"Oversized request blocked - Size: {content_length} - "
                f"Path: {request.url.path} - IP: {request.client.host}"
            )
            raise HTTPException(status_code=413, detail="Request too large")
        
        # Check for suspicious patterns in URL
        full_url = str(request.url)
        for pattern in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, full_url, re.IGNORECASE):
                security_logger.critical(
                    f"Potential attack detected - Pattern: {pattern} - "
                    f"URL: {full_url} - IP: {request.client.host}"
                )
                raise HTTPException(status_code=400, detail="Invalid request")
        
        response = await call_next(request)
        return response

class SecurityMonitoringMiddleware(BaseHTTPMiddleware):
    """Monitor requests for security events"""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Pre-request logging for sensitive endpoints
        sensitive_paths = ["/login", "/admin", "/api/token", "/reset-password"]
        if any(path in request.url.path for path in sensitive_paths):
            security_logger.info(
                f"Sensitive endpoint accessed - Path: {request.url.path} - "
                f"IP: {client_ip} - Method: {request.method}"
            )
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        
        # Detect slow requests (potential DoS)
        if process_time > 5.0:
            security_logger.warning(
                f"Slow request detected - Path: {request.url.path} - "
                f"Duration: {process_time:.2f}s - IP: {client_ip}"
            )
        
        # Log failed authentication attempts
        if response.status_code == 401:
            security_logger.warning(
                f"Failed authentication - Path: {request.url.path} - "
                f"IP: {client_ip} - User-Agent: {user_agent}"
            )
            
            # Track failed attempts per IP
            await track_failed_attempt(client_ip)
        
        # Log forbidden access attempts
        if response.status_code == 403:
            security_logger.warning(
                f"Forbidden access attempt - Path: {request.url.path} - "
                f"IP: {client_ip} - User-Agent: {user_agent}"
            )
        
        return response

# Failed attempt tracking
import redis
from app.config import settings

redis_client = redis.from_url(settings.redis_url) if settings.redis_url else None

async def track_failed_attempt(ip: str):
    """Track failed login attempts per IP"""
    if not redis_client:
        return
    
    key = f"failed_attempts:{ip}"
    
    # Increment counter
    attempts = redis_client.incr(key)
    
    # Set expiration on first attempt
    if attempts == 1:
        redis_client.expire(key, 3600)  # 1 hour window
    
    # Block IP after threshold
    if attempts >= 10:
        security_logger.critical(
            f"IP blocked due to excessive failed attempts - IP: {ip}"
        )
        # Add to blocklist
        redis_client.setex(f"blocked_ip:{ip}", 86400, "1")  # 24 hour block

class IPBlockMiddleware(BaseHTTPMiddleware):
    """Block requests from blacklisted IPs"""
    
    async def dispatch(self, request: Request, call_next):
        if not redis_client:
            return await call_next(request)
        
        client_ip = request.client.host if request.client else None
        
        if client_ip and redis_client.exists(f"blocked_ip:{client_ip}"):
            security_logger.warning(f"Blocked IP attempted access - IP: {client_ip}")
            raise HTTPException(status_code=403, detail="Access denied")
        
        return await call_next(request)

# Rate limiter setup
def get_real_client_ip(request: Request) -> str:
    """Get real client IP considering proxy headers"""
    # Check for proxy headers
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    return request.client.host if request.client else "127.0.0.1"

# Create limiter with custom key function
limiter = Limiter(key_func=get_real_client_ip)