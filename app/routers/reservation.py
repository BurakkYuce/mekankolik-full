from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models,  database
from app.utils import log_activity
from ..schemas import reservation as reservation_schemas
from app.oauth2 import get_current_user
from  ..oauth2 import get_current_user, get_current_business 
from app.database import get_db
from typing import List
from app.schemas.reservation import ReservationCreate, ReservationOut

router = APIRouter(
    prefix="/reservations",
    tags=["Reservations"]
)

@router.post("/", response_model=reservation_schemas.ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(
    reservation: reservation_schemas.ReservationCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Kullanıcı ve işletme doğrulaması
    user = get_current_user(db, reservation.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    business = get_current_business(db, reservation.business_id)
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    # Rezervasyon oluşturma
    new_reservation = models.Reservation(
        user_id=reservation.user_id,
        business_id=reservation.business_id,
        reservation_time=reservation.reservation_time,
        number_of_people=reservation.number_of_people,
        special_requests =reservation.special_requests if reservation.special_requests else None
    )
    
    db.add(new_reservation)
    db.commit()
    db.refresh(new_reservation)

    return new_reservation



router = APIRouter(
    prefix="/reservation",
    tags=["Reservation"]
)

@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=reservation_schemas.ReservationOut)
def create_reservation(
    reservation: ReservationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    business = db.query(models.Business).filter(models.Business.id == reservation.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    new_reservation = models.Reservation(
        user_id=current_user.id,
        status=reservation.status if reservation.status else "pending",
        business_id=reservation.business_id,
        reservation_time=reservation.reservation_time if reservation.reservation_time else None,
        number_of_people=reservation.number_of_people,
        special_requests=reservation.special_requests if reservation.special_requests else None
    )
    db.add(new_reservation)
    db.commit()
    db.refresh(new_reservation)

    new_activity = models.Activity(
        user_id=current_user.id,
        business_id=reservation.business_id,
        action_type="reservation"
    )
    db.add(new_activity)
    db.commit()
    log_activity(db, current_user.id, reservation.business_id, "reservation")
    return new_reservation
