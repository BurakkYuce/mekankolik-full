from datetime import datetime,timezone,timedelta

import pytz

from app.routers import business
from app.routers.rule_engine import create_progress_for_assignment
from .. import models, utils
from ..schemas.campaign import CampaignOut, CampaignUsageOut, CampaignCreate, CampaignUsageCreate, CampaignUsageBase
from ..schemas.reservation import ReservationOut
from fastapi import Depends, FastAPI, Response, status, HTTPException, APIRouter
from sqlalchemy.orm import Session,joinedload
from ..database import get_db
from ..oauth2 import get_current_user,get_current_business
from typing import List
router = APIRouter(
    prefix="/campaign",
    tags=["Campaign"]
)
@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=CampaignOut)
def create_campaign(
    campaign: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Yetki kontrolü
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can create campaigns")

    campaign_data = campaign.dict(exclude_unset=True, exclude={"allowed_business_ids"})
    new_campaign = models.Campaign(**campaign_data)
    db.add(new_campaign)

    # allowed_business_ids varsa doğrula ve eşle
    if campaign.allowed_business_ids:
        for business_id in set(campaign.allowed_business_ids):
            business = db.query(models.Business).filter(models.Business.id == business_id).first()
            if not business:
                raise HTTPException(status_code=404, detail=f"Business with ID {business_id} not found")
            mapping = models.CampaignBusiness(
                campaign=new_campaign,
                business_id=business_id
            )
            db.add(mapping)
    db.commit()
    db.refresh(new_campaign)
    # Kampanyanın business ID’lerini response’a ekle
    new_campaign.allowed_business_ids = [cb.business_id for cb in new_campaign.allowed_businesses]
    return new_campaign

@router.get("/list_all", response_model=List[CampaignOut])
def list_all_campaigns(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Admin kullanıcılar için tüm kampanyaları listele
    if current_user.is_admin:
        campaigns = db.query(models.Campaign).all()
    else:
        # Diğer kullanıcılar için sadece kendi kampanyalarını listele
        campaigns = db.query(models.Campaign).join(models.CampaignAssignment).filter(
            models.CampaignAssignment.user_id == current_user.id
        ).all()
    
    # Her campaign için allowed_business_ids set et
    for campaign in campaigns:
        campaign.allowed_business_ids = [
            cb.business_id for cb in campaign.allowed_businesses
        ]
    
    return campaigns


@router.get("/list", response_model=List[CampaignOut])
def list_my_campaigns(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Şu an aktif ve süresi dolmamış kampanyalar
    now = datetime.now(pytz.timezone("Europe/Istanbul"))

    assignments = db.query(models.CampaignAssignment).join(models.Campaign).filter(
        models.CampaignAssignment.user_id == current_user.id,
        models.CampaignAssignment.is_used == False,
        models.Campaign.start_date <= now,
        models.Campaign.end_date >= now,
        models.Campaign.is_active == True
    ).all()
    
    # ✅ Her campaign için allowed_business_ids set et
    campaigns = []
    for assignment in assignments:
        campaign = assignment.campaign
        # Business ID'lerini manuel olarak ekle
        campaign.allowed_business_ids = [
            cb.business_id for cb in campaign.allowed_businesses
        ]
        campaigns.append(campaign)
    
    return campaigns

@router.post("/assignments/{assignment_id}/use")
def use_campaign(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    assignment = db.query(models.CampaignAssignment).options(
        joinedload(models.CampaignAssignment.campaign)
    ).filter_by(id=assignment_id, user_id=current_user.id).first()

    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if assignment.campaign.is_single_use and assignment.is_used:
        raise HTTPException(status_code=400, detail="Campaign already used")
    
    # Geçerli bir token zaten varsa, tekrar üretme
    if assignment.qr_token and assignment.qr_expires_at:
        if assignment.qr_expires_at > datetime.now(timezone.utc):
            return {
                "qr_token": assignment.qr_token,
                "expires_at": assignment.qr_expires_at
            }
    
    # Yeni token üret
    assignment.qr_token = utils.generate_unique_code()
    assignment.qr_expires_at = datetime.now(timezone.utc) + timedelta(
    minutes=assignment.campaign.usage_duration_minutes
    )
    db.commit()
    db.refresh(assignment)    
    return {
        "qr_token": assignment.qr_token,
        "expires_at": assignment.qr_expires_at
    }


# Bu endpoint'i campaign.py dosyasının EN SONUNA ekle

@router.post("/assign/{campaign_id}/to/{user_id}")
def manually_assign_campaign(
    campaign_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Admin'in manuel olarak bir kullanıcıya kampanya ataması yapmasını sağlar.
    Bu özellikle "static" kampanyalar için gerekli.
    
    Örnek kullanım:
    POST /campaign/assign/5/to/123
    - 5 numaralı kampanyayı, 123 numaralı kullanıcıya atar
    """
    
    # Sadece admin atama yapabilir
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can assign campaigns")
    
    # Kampanya var mı?
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
        
    # Kullanıcı var mı?
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Bu kullanıcıya bu kampanya zaten atanmış mı?
    existing = db.query(models.CampaignAssignment).filter_by(
        user_id=user_id, 
        campaign_id=campaign_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Campaign already assigned to this user")
    
    # Yeni assignment oluştur
    assignment = models.CampaignAssignment(
        user_id=user_id,
        campaign_id=campaign_id,
        assigned_by_rule_engine=False  # Manuel atama olduğu için False
    )
    db.add(assignment)
    db.flush()  # ID almak için
    
    # Progress tracking başlat
    create_progress_for_assignment(assignment, db)
    
    return {
        "message": "Campaign assigned successfully",
        "assignment_id": assignment.id,
        "campaign_title": campaign.title,
        "user_id": user_id
    }