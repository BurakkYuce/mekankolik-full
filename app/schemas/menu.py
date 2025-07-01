from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class MenuItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    image_path: Optional[str] = None  # Dosya yolu veya URL

class MenuItemCreate(MenuItemBase):
    menu_id: int

class MenuItemOut(MenuItemBase):
    id: int

    class Config:
        from_attributes = True


class MenuBase(BaseModel):
    title: str  # Örn: "Kahvaltı", "İçecekler"

class MenuCreate(MenuBase):
    business_id: int

class MenuOut(MenuBase):
    id: int
    items: List[MenuItemOut] = []

    class Config:
        from_attributes = True
