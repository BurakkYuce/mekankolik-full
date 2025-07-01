from pydantic import BaseModel, EmailStr,field_validator
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    phone_number: Optional[str] = None

class UserOut(BaseModel):
    id: int
    email: EmailStr
    phone_number: Optional[str] = None
    profile_photo: Optional[str] = None
    created_at: datetime
    is_active: bool
    is_verified: bool
    class Config:
        from_attributes = True        

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class PhoneUpdateRequest(BaseModel):
    phone_number: str
    @field_validator('phone_number')
    def validate_phone_number(cls, value):
        if not value.isdigit() or len(value) < 10:
            raise ValueError("Phone number must be at least 10 digits long and contain only numbers.")
        return value
    

class EmailUpdateRequest(BaseModel):
    email: EmailStr


