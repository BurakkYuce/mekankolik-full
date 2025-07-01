from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from .. import models
from ..database import get_db
from ..oauth2 import create_access_token, get_current_user
from ..schemas.business import BusinessCreate, BusinessOut, BusinessUpdate
from ..schemas.campaign import CampaignOut, CampaignUsageOut, CampaignCreate, CampaignUsageCreate,CampaignUsageBase
from ..schemas.reservation import ReservationOut
from app import database
from ..utils import verify
from typing import List
from ..schemas.business import BusinessLogin
from ..schemas.token import Token  # dönüş şeması
router = APIRouter(
    prefix="/business",
    tags=["Business"]
)

@router.get("/detail/{id}", response_model=BusinessOut)
def get_business_detail(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    business = db.query(models.Business).filter(models.Business.id == id).first()

    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    return business

@router.put("/update/{id}", response_model=BusinessOut)
def update_business(
    id: int,
    business: BusinessUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    existing_business = db.query(models.Business).filter(
        models.Business.id == id, models.Business.user_id == current_user.id
    ).first()

    if not existing_business:
        raise HTTPException(status_code=404, detail="Business not found")

    update_data = business.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(existing_business, key, value)

    db.commit()
    db.refresh(existing_business)
    return existing_business

@router.post("/{id}/upload-photo")
def upload_business_photo(
    id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1. Business'ı bul
    business = db.query(models.Business).filter(models.Business.id == id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # 2. Yetki kontrolü (ya sahibi ya admin olacak)
    if business.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="You don't have permission to upload a photo for this business")
    
    # 3. Dosya tipi kontrolü
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        raise HTTPException(status_code=400, detail="Invalid file format")

    # 4. Upload klasörü oluştur
    upload_folder = Path(f"app/uploads/business_photos/{id}")
    upload_folder.mkdir(parents=True, exist_ok=True)

    # 5. Dosyayı kaydet
    file_path = upload_folder / file.filename
    with open(file_path, "wb") as f:
        f.write(file.file.read())

    # 6. Veritabanına kaydet
    new_image = models.BusinessImage(business_id=id, path=str(file_path))
    db.add(new_image)
    db.commit()

    return {"status": "success", "photo_path": str(file_path)}

@router.get("/filter", response_model=List[BusinessOut])
def filter_businesses(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    category: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_stars: Optional[float] = None,
    max_stars: Optional[float] = None
):
    query = db.query(models.Business).filter(models.Business.status == models.BusinessStatus.approved)
    
    if category:
        query = query.filter(models.Business.category == category)
    if min_price:
        query = query.filter(models.Business.avg_price >= min_price)
    if max_price:
        query = query.filter(models.Business.avg_price <= max_price)
    if min_stars:
        query = query.filter(models.Business.stars >= min_stars)
    if max_stars:
        query = query.filter(models.Business.stars <= max_stars)

    businesses = query.all()
    
    return businesses


@router.post("/login", response_model=Token)
def login_business(credentials: BusinessLogin, db: Session = Depends(database.get_db)):
    business = db.query(models.Business).filter(
                             models.Business.email == credentials.email,
                             models.Business.branch_code == credentials.branch_code
    ).first()    
    if not business or not verify(credentials.password, business.password):
        raise HTTPException(status_code=403, detail="Invalid credentials")

    # Token'a işletmenin sahibi olan user_id yazılıyor
    access_token = create_access_token(data={"user_id": business.user_id})
    
    return {"access_token": access_token, "token_type": "bearer"}
 

@router.put("/confirmReservation/{id}", response_model=BusinessOut)
def confirm_reservation(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == id).first()
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    
    if reservation.status != "pending":
        raise HTTPException(status_code=400, detail="Reservation is not pending")
    
    reservation.status = "confirmed"
    db.commit()
    db.refresh(reservation)
    
    return reservation

@router.put("/cancelReservation/{id}", response_model=BusinessOut)
def confirm_reservation(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == id).first()
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")
    

    
    reservation.status = "cancelled"
    db.commit()
    db.refresh(reservation)
    
    return reservation

@router.put("/handle-reservation/{reservation_id}")
def handle_reservation_status(
    reservation_id: int,
    action: str,  # 'confirm' veya 'cancel'
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    # Yetki: Bu işletmenin sahibi mi?
    business = db.query(models.Business).filter(models.Business.id == reservation.business_id).first()
    if business.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this reservation")

    if action == "confirm":
        reservation.status = "confirmed"
    elif action == "cancel":
        reservation.status = "cancelled"
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    db.commit()
    db.refresh(reservation)
    return {"status": reservation.status}
