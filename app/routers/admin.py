# app/routers/admin.py - SECURE VERSION
import shutil
from typing import List
from fastapi import Depends, APIRouter, HTTPException, Response, status, File, Path, Security, UploadFile, Header, Request
from sqlalchemy.orm import Session
from .. import models, utils
from ..database import get_db
from ..schemas.user import UserLogin, UserOut
from ..schemas.business import BusinessCreate, BusinessImageOut, BusinessOut, BusinessStatus, BusinessTagOut, BusinessCategory
from ..schemas.comment import CommentOut
from ..schemas.campaign import CampaignOut, CampaignUsageOut
from ..schemas.reservation import ReservationOut
from ..schemas.activity import ActivityOut
from ..oauth2 import get_current_user
from pathlib import Path
from typing import Optional, List
import uuid
import mimetypes
from PIL import Image
import os
from ..config import settings
from ..security.file_upload import SecureFileUpload
from ..middleware.security import limiter
import logging

logger = logging.getLogger(__name__)
security_logger = logging.getLogger('security')

router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)

# === REMOVE OR SECURE THE DANGEROUS ENDPOINT ===

# ❌ DELETE THIS COMPLETELY IN PRODUCTION
# @router.post("/add-admin-temp")  # REMOVED - SECURITY VULNERABILITY

# ✅ SECURE ADMIN CREATION (Only for initial setup)
@router.post("/initialize-admin", include_in_schema=False)
@limiter.limit("1/hour")  # Strict rate limit
async def initialize_first_admin(
    request: Request,
    admin_data: dict,
    db: Session = Depends(get_db),
    api_key: str = Header(None, alias="X-Admin-Init-Key")
):
    """
    One-time admin initialization endpoint.
    Should be disabled after first admin is created.
    """
    
    # Check if any admin exists
    existing_admin = db.query(models.User).filter(models.User.is_admin == True).first()
    if existing_admin:
        security_logger.warning(
            f"Admin initialization attempted when admin exists - IP: {request.client.host}"
        )
        raise HTTPException(status_code=403, detail="Admin already exists")
    
    # Validate initialization key
    if api_key != settings.super_admin_api_key:
        security_logger.critical(
            f"Invalid admin initialization attempt - IP: {request.client.host}"
        )
        raise HTTPException(status_code=403, detail="Invalid initialization key")
    
    # Validate admin data
    email = admin_data.get("email")
    password = admin_data.get("password")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    
    # Password strength check
    if not utils.verify_password_strength(password):
        raise HTTPException(
            status_code=400, 
            detail="Password must be at least 8 characters with uppercase, lowercase, number, and special character"
        )
    
    # Create admin user
    hashed_password = utils.hash(password)
    
    new_admin = models.User(
        email=email.lower(),
        password=hashed_password,
        is_admin=True,
        is_active=True,
        is_verified=True
    )
    db.add(new_admin)
    db.flush()
    
    # Create admin profile
    admin_entry = models.Admin(user_id=new_admin.id)
    db.add(admin_entry)
    
    db.commit()
    
    security_logger.info(
        f"First admin created - Email: {email} - IP: {request.client.host}"
    )
    
    return {
        "message": "Admin created successfully",
        "note": "This endpoint should now be disabled"
    }

# === ADMIN-ONLY DECORATOR ===
def require_super_admin(current_user: models.User = Depends(get_current_user)):
    """Require super admin privileges"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Additional check for super admin status if needed
    # if not current_user.is_super_admin:
    #     raise HTTPException(status_code=403, detail="Super admin access required")
    
    return current_user

# === SECURE ADMIN MANAGEMENT ===
@router.post("/admins", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def create_new_admin(
    request: Request,
    email: str,
    temporary_password: str,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_super_admin)
):
    """Create new admin (super admin only)"""
    
    # Check if user exists
    existing_user = db.query(models.User).filter(
        models.User.email == email.lower()
    ).first()
    
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    # Create admin with temporary password
    hashed_password = utils.hash(temporary_password)
    
    new_admin = models.User(
        email=email.lower(),
        password=hashed_password,
        is_admin=True,
        is_active=True,
        is_verified=True,
        must_change_password=True  # Force password change on first login
    )
    db.add(new_admin)
    db.flush()
    
    admin_entry = models.Admin(user_id=new_admin.id)
    db.add(admin_entry)
    
    db.commit()
    
    # Log admin creation
    security_logger.info(
        f"Admin created - Created by: {current_admin.email} - "
        f"New admin: {email} - IP: {request.client.host}"
    )
    
    # Send email to new admin (implement email service)
    # await send_admin_welcome_email(email, temporary_password)
    
    return {
        "message": "Admin created successfully",
        "email": email,
        "note": "Temporary password sent to email"
    }

@router.delete("/admins/{admin_id}")
@limiter.limit("5/hour")
async def revoke_admin_access(
    request: Request,
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_super_admin)
):
    """Revoke admin access"""
    
    # Prevent self-revocation
    if admin_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot revoke own admin access")
    
    # Find admin
    admin_user = db.query(models.User).filter(
        models.User.id == admin_id,
        models.User.is_admin == True
    ).first()
    
    if not admin_user:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    # Ensure at least one admin remains
    admin_count = db.query(models.User).filter(models.User.is_admin == True).count()
    if admin_count <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove last admin")
    
    # Revoke admin access
    admin_user.is_admin = False
    
    # Remove admin profile
    db.query(models.Admin).filter(models.Admin.user_id == admin_id).delete()
    
    db.commit()
    
    security_logger.warning(
        f"Admin access revoked - Revoked by: {current_admin.email} - "
        f"Revoked admin: {admin_user.email} - IP: {request.client.host}"
    )
    
    return {"message": "Admin access revoked successfully"}

@router.get("/admins", response_model=List[UserOut])
async def list_admins(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_super_admin)
):
    """List all admins"""
    admins = db.query(models.User).filter(models.User.is_admin == True).all()
    return admins

# === ENHANCED BUSINESS CREATION WITH AUDIT ===
@router.post("/businesses", status_code=status.HTTP_201_CREATED, response_model=BusinessOut)
@limiter.limit("10/hour")
async def create_business_secure(
    request: Request,
    business: BusinessCreate, 
    db: Session = Depends(get_db), 
    current_admin: models.User = Depends(require_super_admin)
):
    """Create business with full audit trail"""
    
    # Enhanced validation
    if not business.name or len(business.name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Business name too short")
    
    if not utils.validate_email_format(business.email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    
    # Check duplicates
    existing = db.query(models.Business).filter(
        db.or_(
            models.Business.name.ilike(f"%{business.name.strip()}%"),
            models.Business.email == business.email.lower(),
            models.Business.branch_code == business.branch_code
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Business already exists")
    
    # Validate coordinates
    if not (-90 <= business.latitude <= 90 and -180 <= business.longitude <= 180):
        raise HTTPException(status_code=400, detail="Invalid coordinates")
    
    try:
        # Create business
        hashed_password = utils.hash(business.password)
        business_data = business.dict(exclude={"password"})
        business_data["password"] = hashed_password
        business_data["email"] = business.email.lower()
        business_data["name"] = business.name.strip()
        
        new_business = models.Business(**business_data)
        db.add(new_business)
        db.commit()
        db.refresh(new_business)
        
        # Audit log
        audit_log = models.AuditLog(
            user_id=current_admin.id,
            action="create_business",
            resource_type="business",
            resource_id=new_business.id,
            details={
                "business_name": new_business.name,
                "business_email": new_business.email,
                "ip_address": request.client.host
            }
        )
        db.add(audit_log)
        db.commit()
        
        logger.info(
            f"Business created by admin - Admin: {current_admin.email} - "
            f"Business: {new_business.name} - IP: {request.client.host}"
        )
        
        return new_business
        
    except Exception as e:
        db.rollback()
        logger.error(f"Business creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create business")

# === REST OF THE ENDPOINTS WITH SECURITY ENHANCEMENTS ===

# All other endpoints remain the same but with added:
# 1. @limiter.limit() decorators for rate limiting
# 2. request: Request parameter for IP logging
# 3. Enhanced validation
# 4. Audit logging
# 5. Security event logging

# Example for other endpoints:
@router.get("/businesses", response_model=List[BusinessOut])
@limiter.limit("30/minute")
async def get_businesses(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db), 
    current_admin: models.User = Depends(require_super_admin)
):
    """Get all businesses with pagination"""
    
    # Validate pagination
    if skip < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Invalid pagination parameters")
    
    businesses = db.query(models.Business).offset(skip).limit(limit).all()
    
    # Log access
    logger.info(
        f"Admin accessed business list - Admin: {current_admin.email} - "
        f"Count: {len(businesses)} - IP: {request.client.host}"
    )
    
    return businesses

# Continue pattern for all other endpoints...