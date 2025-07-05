# app/middleware/admin_protection.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)
security_logger = logging.getLogger('security')

async def require_admin_middleware(request: Request, call_next):
    """
    Middleware to protect admin routes
    Additional security layer for admin endpoints
    """
    # Log admin access attempt
    client_ip = request.client.host if request.client else "unknown"
    security_logger.info(
        f"Admin endpoint accessed - Path: {request.url.path} - IP: {client_ip}"
    )
    
    # You can add additional checks here like:
    # - IP whitelist verification
    # - Time-based access restrictions
    # - Additional authentication headers
    
    response = await call_next(request)
    
    # Log response
    if response.status_code >= 400:
        security_logger.warning(
            f"Admin endpoint error - Path: {request.url.path} - "
            f"Status: {response.status_code} - IP: {client_ip}"
        )
    
    return response