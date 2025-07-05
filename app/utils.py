from datetime import datetime, timezone
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
    """Kullanici aktivitesini loglar"""
    activity = models.Activity(
        user_id=user_id,
        business_id=business_id,
        action_type=action_type
    )
    db.add(activity)
    db.commit()

def update_campaign_progress(db: Session, user_id: int, action_type: str, **kwargs):
    """Kullanicinin kampanya progress'ini günceller"""
    
    # Aktif campaign assignment'ları bul
    active_assignments = db.query(models.CampaignAssignment).join(models.Campaign).filter(
        models.CampaignAssignment.user_id == user_id,
        models.CampaignAssignment.is_used == False,
        models.Campaign.is_active == True,
        models.Campaign.start_date <= datetime.utcnow(),
        models.Campaign.end_date >= datetime.utcnow()
    ).all()
    
    for assignment in active_assignments:
        # Progress kaydı var mı kontrol et
        progress = db.query(models.CampaignProgress).filter_by(
            assignment_id=assignment.id
        ).first()
        
        if not progress:
            # Yeni progress kaydı oluştur
            progress = models.CampaignProgress(
                assignment_id=assignment.id,
                user_id=user_id,
                campaign_id=assignment.campaign_id
            )
            db.add(progress)
            db.flush()  # ID almak için
        
        # Action type'a göre güncelle
        if action_type == "comment":
            progress.comments_made += 1
            
        elif action_type == "reservation":
            progress.reservations_made += 1
            
            # ✅ Businesses visited kontrolü - daha basit yaklaşım
            if "business_id" in kwargs:
                business_id = kwargs["business_id"]
                
                # Bu kullanıcının daha önce bu business'a rezervasyon yapıp yapmadığını kontrol et
                previous_reservation = db.query(models.Reservation).filter(
                    models.Reservation.user_id == user_id,
                    models.Reservation.business_id == business_id,
                    models.Reservation.id != None  # Mevcut reservation hariç (ama henüz commit edilmedi)
                ).first()
                
                # Eğer ilk kez bu business'a rezervasyon yapıyorsa
                if not previous_reservation:
                    progress.businesses_visited += 1
                    
        elif action_type == "purchase" and "amount" in kwargs:
            progress.total_spend += kwargs["amount"]
        
        progress.last_updated = datetime.utcnow()
        
    # ✅ Tek commit yap
    db.commit()