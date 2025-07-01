from typing import List
from fastapi import Depends, APIRouter, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, utils
from ..database import get_db
from ..schemas.user import EmailUpdateRequest, PasswordChangeRequest, PhoneUpdateRequest, UserLogin, UserOut, UserCreate
from ..schemas.comment import CommentOut
from ..schemas.campaign import CampaignOut, CampaignUsageOut,CampaignAssignmentOut
from ..schemas.reservation import ReservationOut
from ..schemas.activity import ActivityOut  # varsa
from ..oauth2 import get_current_user
from pathlib import Path
from typing import List
from datetime import datetime, timedelta


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
    CampaignOut = db.query(models.CampaignAssignment).filter(models.CampaignAssignment.user_id == current_user.id).all()

    # allowed_business_ids'i her kampanya için ekle
    for CampaignOut in CampaignOut:
        CampaignOut.allowed_business_ids = [
            cb.business_id for cb in CampaignOut.allowed_businesses
        ]

    return CampaignOut  

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
        reservation = db.query(models.Reservation).filter(
            models.Reservation.id == reservation_id,
            models.Reservation.user_id == current_user.id
        ).first()
        
        if not reservation:
            raise HTTPException(status_code=404, detail="Reservation not found")

        if reservation.reservation_time - timedelta(hours=1) <= datetime.utcnow():
            raise HTTPException(status_code=400, detail="You cannot cancel less than 1 hour before reservation time")

        reservation.status = ReservationStatus.cancelled  # Enum ataması
        db.commit()
        db.refresh(reservation)
        return {"detail": "Reservation cancelled successfully"}

    except Exception as e:
        logger.exception("An error occurred while cancelling reservation ,reservation time already passed or missed")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
