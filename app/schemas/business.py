from pydantic import BaseModel, EmailStr
from typing import Optional, List
from enum import Enum
from datetime import datetime
from .menu import MenuOut
from .comment import CommentOut
from .campaign import CampaignOut
from .reservation import ReservationOut  



class BusinessCategory(str, Enum):
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    BARBERSHOP = "barbershop"
    HOTEL = "hotel"
    OTHER = "other"

class BusinessStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class BusinessBase(BaseModel):
    name: str
    description: Optional[str] = None
    branch_code: str  # Benzersiz kod, işletme sahibi için
    phone: Optional[str] = None
    email: EmailStr
    latitude: float
    password: str 
    longitude: float
    avg_price: Optional[int] = None
    stars: Optional[float] = None
    working_hours: Optional[str] = None
    category: BusinessCategory = BusinessCategory.OTHER
    status: Optional[BusinessStatus] = BusinessStatus.APPROVED
    class Config:
        from_attributes = True

class BusinessImageOut(BaseModel):
    id: int
    business_id: int
    path: str  # Örn: "uploads/business/42/main.jpg"

    class Config:
        from_attributes = True

class BusinessCreate(BusinessBase):
    user_id: int 

class BusinessTagOut(BaseModel):
    id: int
    business_id: int
    tag: str  # Örn: "vegan", "wifi", "bahçeli"

    class Config:
        from_attributes = True


class BusinessOut(BusinessBase):
    id: int
    created_at: datetime
    menus: List[MenuOut] = []
    comments: List[CommentOut] = []
    tags: List[BusinessTagOut] = []
    images: List[BusinessImageOut] = []
    campaigns: List[CampaignOut] = []
    reservations: List[ReservationOut] = []

    class Config:
        from_attributes = True

class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    avg_price: Optional[int] = None
    stars: Optional[float] = None
    working_hours: Optional[str] = None
    category: Optional[BusinessCategory] = None
    status: Optional[BusinessStatus] = None

    class Config:
        from_attributes = True    

BusinessOut.model_rebuild()
# En alta ekle:
class BusinessLogin(BaseModel):
    email: EmailStr
    branch_code: str  # İşletme sahibi için benzersiz kod
    password: str
    class Config:
        from_attributes = True
        