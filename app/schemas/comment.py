from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CommentBase(BaseModel):
    text: str
    rating: float  

class CommentCreate(CommentBase):
    user_id: int
    business_id: Optional[int] = None
    menu_item_id: Optional[int] = None

class CommentOut(CommentBase):
    id: int
    created_at: datetime
    user_id: int
    business_id: Optional[int] = None
    menu_item_id: Optional[int] = None

    class Config:
        from_attributes = True
