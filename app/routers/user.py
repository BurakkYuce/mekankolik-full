from typing import List
from fastapi import Depends, APIRouter, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, utils
from ..database import get_db
from ..schemas.user import EmailUpdateRequest, PasswordChangeRequest, PhoneUpdateRequest, UserLogin, UserOut, UserCreate
from ..schemas.comment import CommentOut
from ..schemas.campaign import CampaignOut, CampaignUsageOut,CampaignAssignmentOut
from ..schemas.reservation import ReservationOut
from ..schemas.activity import ActivityOut  
from ..oauth2 import get_current_user
from pathlib import Path
from typing import List
from datetime import datetime, timedelta,timezone


router = APIRouter(
    prefix="/user",
    tags=["User"]
)
# ✅ Kendi profil Bilgilerini Getirme
@router.get("/me", response_model=UserOut)
def get_user_me(current_user: models.User = Depends(get_current_user)):
    return current_user
# ✅ KULLANICI OLUŞTURMA
@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    user.password = utils.hash(user.password)

    if db.query(models.User).filter(models.User.email == user.email.lower()).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    new_user = models.User(**user.dict())
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
# ✅ KULLANICI GETİRME
@router.get("/{id}", response_model=UserOut)
def get_user(id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"user with id {id} was not found")
    return user 


# ✅ E-POSTA GÜNCELLEME
@router.put("/me/update-email", response_model=UserOut)
def update_email(data: EmailUpdateRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.email = data.email
    db.commit()
    db.refresh(user)
    return user
# ✅ TELEFON GÜNCELLEME
@router.put("/me/update-phone", response_model=UserOut)
def update_phone(data: PhoneUpdateRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if db.query(models.User).filter(models.User.phone_number == data.phone_number).first():
        raise HTTPException(status_code=400, detail="Phone number already registered")

    
    user.phone_number = data.phone_number
    db.commit()
    db.refresh(user)
    return user
# ✅ ŞİFRE DEĞİŞTİRME
@router.put("/me/change-password", response_model=UserOut)
def change_password(data: PasswordChangeRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not utils.verify(data.current_password, user.password):
        raise HTTPException(status_code=403, detail="Current password is incorrect")

    user.password = utils.hash(data.new_password)
    db.commit()
    db.refresh(user)
    return user



@router.get("/users/{user_id}/comments", response_model=List[CommentOut])
def get_comments_by_user(current_user: models.User=Depends(get_current_user), db: Session = Depends(get_db)):
    user_id= current_user.id
    return db.query(models.Comment).filter(models.Comment.user_id == user_id).all()

@router.get("/me/campaigns", response_model=List[CampaignOut])
def get_my_campaigns(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    assignments = (
        db.query(models.CampaignAssignment)
        .filter(models.CampaignAssignment.user_id == current_user.id)
        .all()
    )

    campaigns = []
    for assignment in assignments:
        campaign = assignment.campaign
        if campaign:
            # CampaignOut içindeki allowed_business_ids alanını doldur
            campaign_out = CampaignOut.model_validate(campaign)
            campaign_out.allowed_business_ids = [cb.business_id for cb in campaign.allowed_businesses]
            campaign_out.assignments = [CampaignAssignmentOut.model_validate(assignment)]
            campaigns.append(campaign_out)

    return campaigns

# ✅ KULLANDIĞI KAMPANYALAR
@router.get("/me/used-campaigns", response_model=List[CampaignUsageOut])
def get_my_used_campaigns(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.CampaignUsage).filter(models.CampaignUsage.user_id == current_user.id).all()

# ✅ REZERVASYONLARIM
@router.get("/me/reservations", response_model=List[ReservationOut])
def get_my_reservations(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Reservation).filter(models.Reservation.user_id == current_user.id).all()

# ✅ GEÇMİŞ AKTİVİTELER (isteğe bağlı)
@router.get("/me/activities", response_model=List[ActivityOut])
def get_my_activities(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Activity).filter(models.Activity.user_id == current_user.id).all()

@router.get("/me/comments",response_model=List[CommentOut])
def get_my_comments(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Comment).filter(models.Comment.user_id == current_user.id).all()


from app.schemas.reservation import ReservationStatus
import logging

logger = logging.getLogger(__name__)

@router.put("/cancel-reservation/{reservation_id}")
def user_cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        # Rezervasyonu bul
        reservation = db.query(models.Reservation).filter(
            models.Reservation.id == reservation_id,
            models.Reservation.user_id == current_user.id
        ).first()
        
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        # ✅ Durum kontrolü ekle - zaten cancel edilmiş mi?
        if reservation.status == ReservationStatus.cancelled:
            raise HTTPException(
                status_code=400, 
                detail="Reservation is already cancelled"
            )
        
        # ✅ Completed veya rejected rezervasyonlar cancel edilemez
        if reservation.status in [ReservationStatus.completed, ReservationStatus.rejected]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot cancel reservation with status: {reservation.status}"
            )

        # ✅ Zaman kontrolü - 1 saat öncesine kadar iptal edilebilir
        if reservation.reservation_time - timedelta(hours=1) <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=400, 
                detail="You cannot cancel less than 1 hour before reservation time"
            )

        # ✅ Durumu güncelle
        reservation.status = ReservationStatus.cancelled
        db.commit()
        db.refresh(reservation)
        
        logger.info(f"Reservation {reservation_id} cancelled by user {current_user.id}")
        
        return {
            "detail": "Reservation cancelled successfully",
            "reservation_id": reservation_id,
            "status": reservation.status
        }

    except HTTPException:
        # HTTPException'ları olduğu gibi yeniden fırlat
        raise
    except Exception as e:
        # Beklenmeyen hatalar için
        logger.exception(f"Unexpected error while cancelling reservation {reservation_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="An unexpected error occurred while cancelling the reservation"
        )
    
    
@router.get("/reservations/{reservation_id}/status")
def get_reservation_status(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    reservation = db.query(models.Reservation).filter(
        models.Reservation.id == reservation_id,
        models.Reservation.user_id == current_user.id
    ).first()
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    time_until_reservation = reservation.reservation_time - datetime.now(timezone.utc)
    can_cancel = (
        reservation.status in [ReservationStatus.pending, ReservationStatus.confirmed] and
        time_until_reservation > timedelta(hours=1)
    )
    
    return {
        "reservation_id": reservation_id,
        "status": reservation.status,
        "can_cancel": can_cancel,
        "time_until_reservation": str(time_until_reservation),
        "reservation_time": reservation.reservation_time
    }