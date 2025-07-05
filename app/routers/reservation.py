from datetime import datetime,timezone
from fastapi import APIRouter, Depends, HTTPException, logger, status
from sqlalchemy.orm import Session
from app import models,  database
from app import utils
from app.utils import log_activity
from ..schemas import reservation as reservation_schemas
from app.oauth2 import get_current_user
from  ..oauth2 import get_current_user, get_current_business 
from app.database import get_db
from typing import List
from app.schemas.reservation import ReservationCreate, ReservationOut
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/reservations",
    tags=["Reservations"]
)


@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=reservation_schemas.ReservationOut)
def create_reservation(
    reservation: ReservationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        # ✅ Kullanıcı ve işletme doğrulaması
        if not current_user:
            raise HTTPException(status_code=401, detail="Unauthorized user")
            
        # ✅ Input validation
        if reservation.number_of_people <= 0:
            raise HTTPException(status_code=400, detail="Number of people must be positive")
        
        if reservation.number_of_people > 20:  # Makul bir limit
            raise HTTPException(status_code=400, detail="Maximum 20 people per reservation")

        # ✅ Reservation time validation
        if reservation.reservation_time:
            if reservation.reservation_time <= datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="Reservation time must be in the future")

        # Yeni reservation oluştur
        new_reservation = models.Reservation(
            user_id=current_user.id,
            status=reservation.status if reservation.status else "pending",
            business_id=reservation.business_id,
            reservation_time=reservation.reservation_time,
            number_of_people=reservation.number_of_people,
            special_requests=reservation.special_requests if reservation.special_requests else None
        )
        
        db.add(new_reservation)
        db.commit()
        db.refresh(new_reservation)

        # ✅ Campaign progress güncelle (businesses_visited mantığı olmadan)
        utils.update_campaign_progress(db, current_user.id, "reservation", business_id=reservation.business_id)
        
        # ✅ Activity logla (tek sefer)
        utils.log_activity(db, current_user.id, reservation.business_id, "reservation")
        
        return new_reservation

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating reservation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create reservation")