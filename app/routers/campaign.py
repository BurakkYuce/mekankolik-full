from datetime import datetime,timezone,timedelta

import pytz

from app.routers import business
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

@router.get("/list", response_model=List[CampaignOut])
def list_campaigns(
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
        
    return [a.campaign for a in assignments]


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
        if assignment.qr_expires_at > datetime.utcnow():
            return {
                "qr_token": assignment.qr_token,
                "expires_at": assignment.qr_expires_at
            }
    # Yeni token üret
    assignment.qr_token = utils.generate_unique_code()
    assignment.qr_expires_at = datetime.utcnow() + timedelta(
        minutes=assignment.campaign.usage_duration_minutes
    )
    db.commit()
    db.refresh(assignment)
    utils.log_activity(db, current_user.id, business.id, "campaign_usage")
    return {
        "qr_token": assignment.qr_token,
        "expires_at": assignment.qr_expires_at
    }

