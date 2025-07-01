from passlib.context import CryptContext
import secrets
from sqlalchemy.orm import Session
from app import models
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def hash(password: str):
    return pwd_context.hash(password)

def verify(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def generate_unique_code(length=8):
    return secrets.token_urlsafe(length)  


def log_activity(db: Session, user_id: int, business_id: int, action_type: str):
    activity = models.Activity(
        user_id=user_id,
        business_id=business_id,
        action_type=action_type
    )
    db.add(activity)
    db.commit()
