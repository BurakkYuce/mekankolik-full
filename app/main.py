# app/main.py - Secure version with all security features
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
import logging
import sys
import time
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import APIRouter

# Import all routers
from app import models
from app.routers import admin, business, comment, user, auth, campaign, reservation
from app.database import engine, SessionLocal
from app.config import settings
from sqlalchemy import text
logger = logging.getLogger(__name__)
# Import security components
try:
    from app.middleware.security import (
        SecurityHeadersMiddleware,
        RequestValidationMiddleware,
        SecurityMonitoringMiddleware,
        IPBlockMiddleware,
        limiter,
        security_logger
    )
    from slowapi.errors import RateLimitExceeded
    from slowapi import _rate_limit_exceeded_handler
    SECURITY_MIDDLEWARE_AVAILABLE = True
except ImportError:
    logger.warning("Security middleware not available - running without enhanced security")
    SECURITY_MIDDLEWARE_AVAILABLE = False
    # Create dummy objects
    class DummyMiddleware:
        def __init__(self, app):
            self.app = app
        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)
    
    SecurityHeadersMiddleware = DummyMiddleware
    RequestValidationMiddleware = DummyMiddleware
    SecurityMonitoringMiddleware = DummyMiddleware
    IPBlockMiddleware = DummyMiddleware

# Logging configuration
logging.basicConfig(
    level=logging.INFO if not settings.is_production() else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Lifespan manager for startup/shutdown tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting FastAPI application...")
    
    # Create database tables
    models.Base.metadata.create_all(bind=engine)
    
    # Initialize security components
    logger.info("Security components initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down FastAPI application...")

# Create FastAPI app with security configurations

app = FastAPI(
    title="Mekankolik API",
    description="Secure FastAPI Application with Authentication",
    version="1.0.0",
    docs_url="/docs",  # Force enable
    redoc_url="/redoc",  # Force enable
    openapi_url="/openapi.json",  # Force enable
    lifespan=lifespan
)

# Apply rate limiter
if SECURITY_MIDDLEWARE_AVAILABLE:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# === MIDDLEWARE ORDER MATTERS - Most restrictive first ===

# 1. IP Blocking (reject bad IPs immediately)
app.add_middleware(IPBlockMiddleware)

# 2. Trusted Host (reject invalid hosts)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts if settings.is_production() else ["*"]
)

# 3. Request Validation (check for malicious patterns)
app.add_middleware(RequestValidationMiddleware)

# 4. Session Security
app.add_middleware(
    SessionMiddleware,
    secret_key=secrets.token_urlsafe(32),
    same_site="strict",
    https_only=settings.is_production(),
    max_age=3600  # 1 hour sessions
)

# 5. CORS (configure allowed origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
        "https://yourdomain.com"
    ] if settings.is_production() else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Request-ID"]
)

# 6. Security Headers (add headers to responses)
#app.add_middleware(SecurityHeadersMiddleware)

# 7. Security Monitoring (log security events)
app.add_middleware(SecurityMonitoringMiddleware)

# === EXCEPTION HANDLERS ===

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Secure HTTP exception handler"""
    
    # Log security-relevant errors
    if exc.status_code in [401, 403, 429]:
        client_ip = request.client.host if request.client else "unknown"
        if SECURITY_MIDDLEWARE_AVAILABLE:
            security_logger.warning(
                f"HTTP {exc.status_code} - Path: {request.url.path} - "
                f"IP: {client_ip} - Detail: {exc.detail}"
            )
        else:
            logger.warning(
                f"HTTP {exc.status_code} - Path: {request.url.path} - "
                f"IP: {client_ip} - Detail: {exc.detail}"
            )
    
    # Hide internal details in production
    if settings.is_production() and exc.status_code == 500:
        request_id = getattr(request.state, 'request_id', 'no-id')
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id}
        )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail)}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Secure validation error handler"""
    
    logger.warning(f"Validation error on {request.url.path}: {exc.errors()}")
    
    if settings.is_production():
        # Don't expose field details in production
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid input data"}
        )
    
    # Development: show detailed errors
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler"""
    
    import traceback
    error_id = secrets.token_urlsafe(16)
    
    # Log full error with ID
    logger.error(f"Unhandled exception [{error_id}]: {traceback.format_exc()}")
    
    # Check for potential security issues
    error_str = str(exc).lower()
    if any(term in error_str for term in ['sql', 'injection', 'hack', 'attack']):
        if SECURITY_MIDDLEWARE_AVAILABLE:
            security_logger.critical(
                f"Potential security incident [{error_id}] - "
                f"Path: {request.url.path} - Error: {str(exc)}"
            )
        else:
            logger.critical(
                f"Potential security incident [{error_id}] - "
                f"Path: {request.url.path} - Error: {str(exc)}"
            )
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_id": error_id,
            "message": "Please contact support with this error ID"
        }
    )

# === REQUEST TRACKING MIDDLEWARE ===
# NOT: Middleware'ler ters sırada çalışır (sondan başa)
# Bu yüzden önce log_requests, sonra add_request_id tanımlanmalı

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing"""
    start_time = time.time()
    
    # Skip health checks
    if request.url.path == "/health":
        return await call_next(request)
    
    client_ip = request.client.host if request.client else "unknown"
    
    # Log request
    logger.info(f"Request [{getattr(request.state, 'request_id', 'no-id')}] - {request.method} {request.url.path} - IP: {client_ip}")
    
    response = await call_next(request)
    
    # Log response with timing
    process_time = time.time() - start_time
    logger.info(
        f"Response [{getattr(request.state, 'request_id', 'no-id')}] - "
        f"Status: {response.status_code} - "
        f"Duration: {process_time:.2f}s"
    )
    
    # Add timing header
    response.headers["X-Process-Time"] = str(process_time)
    
    return response

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add unique request ID for tracking"""
    request_id = request.headers.get("X-Request-ID", secrets.token_urlsafe(16))
    request.state.request_id = request_id
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    return response

# === HEALTH & MONITORING ENDPOINTS ===

@app.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "environment": settings.environment
    }

@app.get("/health/detailed")
async def detailed_health_check(
    api_key: str = Header(None)
):
    """Detailed health check (requires API key)"""
    if api_key != settings.monitoring_api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Check database
    try:
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_status = "healthy"
    except:
        db_status = "unhealthy"
    
    # Check Redis (if configured)
    redis_status = "not configured"
    if settings.redis_url:
        try:
            import redis
            r = redis.from_url(settings.redis_url)
            r.ping()
            redis_status = "healthy"
        except:
            redis_status = "unhealthy"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "database": db_status,
            "redis": redis_status,
            "api": "healthy"
        },
        "metrics": {
            "memory_usage_mb": get_memory_usage()
        }
    }

# === INCLUDE ROUTERS ===

# Public routes
app.include_router(auth.router)
app.include_router(user.router)

# Protected routes
app.include_router(business.router)
app.include_router(reservation.router)
app.include_router(comment.router)
app.include_router(campaign.router)

# Admin routes (add extra protection if needed)
# from app.middleware.admin_protection import require_admin_middleware
# admin_router = APIRouter(prefix="/admin", tags=["Admin"])
# admin_router.middleware("http")(require_admin_middleware)
app.include_router(admin.router)

# === ROOT ENDPOINT ===

@app.get("/")
async def root():
    """Root endpoint - minimal information"""
    return {
        "message": "API is running",
        "documentation": "/docs" if not settings.is_production() else "Disabled in production",
        "health": "/health"
    }

# === UTILITY FUNCTIONS ===

def get_memory_usage():
    """Get current memory usage in MB"""
    try:
        import psutil
        import os
        process = psutil.Process(os.getpid())
        return round(process.memory_info().rss / 1024 / 1024, 2)
    except:
        return 0  # Return 0 if psutil not installed

# === STARTUP BANNER ===

if __name__ == "__main__":
    import uvicorn
    
    security_status = "ENABLED" if SECURITY_MIDDLEWARE_AVAILABLE else "LIMITED"
    
    print(f"""
    ╔══════════════════════════════════════╗
    ║     🔒 SECURE FASTAPI SERVER 🔒      ║
    ╠══════════════════════════════════════╣
    ║  Environment: {settings.environment:<22} ║
    ║  Debug Mode: {str(settings.debug):<23} ║
    ║  Security: {security_status:<25} ║
    ╚══════════════════════════════════════╝
    """)
    
    # Run with appropriate settings
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",  # Only localhost in dev
        port=8000,
        reload=not settings.is_production(),
        access_log=not settings.is_production(),
        ssl_keyfile="certs/key.pem" if settings.is_production() else None,
        ssl_certfile="certs/cert.pem" if settings.is_production() else None
    )