from typing import Optional
from datetime import datetime
from pydantic import BaseModel
class ActivityOut(BaseModel):
    id: int
    user_id: int
    business_id: int
    action_type: str
    description: Optional[str] = None  # NULL gelebileceği için
    timestamp: Optional[datetime] = None  # NULL gelebileceği için

    class Config:
        orm_mode = True
