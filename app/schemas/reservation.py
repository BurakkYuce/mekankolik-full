import enum
from pydantic import BaseModel
from ..models import ReservationStatus
from datetime import datetime

class ReservationBase(BaseModel):
    user_id: int
    status:ReservationStatus
    business_id: int
    reservation_time: datetime  
    number_of_people: int
    special_requests: str

class ReservationCreate(ReservationBase):
    pass

class ReservationOut(ReservationBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True



