import shutil
from typing import List
from fastapi import Depends, APIRouter, HTTPException, Response, status,File ,Path,Security,UploadFile
from sqlalchemy.orm import Session
from .. import models, utils
from ..database import get_db
from ..schemas.user import UserLogin, UserOut
from ..schemas.business import BusinessCreate,BusinessImageOut,BusinessOut,BusinessStatus,BusinessTagOut,BusinessCategory
from ..schemas.comment import CommentOut
from ..schemas.campaign import CampaignOut, CampaignUsageOut
from ..schemas.reservation import ReservationOut
from ..schemas.activity import ActivityOut  # varsa
from ..oauth2 import get_current_user
from pathlib import Path
from typing import Optional,List


router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)
@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=BusinessOut)
def create_business(business: BusinessCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Admin kontrolü
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create a business")
    
    # Aynı isimde işletme var mı?
    existing_business = db.query(models.Business).filter(models.Business.name == business.name).first()
    if existing_business:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Business already exists")
    
    # Şifreyi hashle
    hashed_password = utils.hash(business.password)

    # Yeni business oluştur
    business_data = business.dict(exclude={"user_id"})
    business_data["password"] = hashed_password

    new_business = models.Business(**business_data, user_id=current_user.id)
    db.add(new_business)
    db.commit()
    db.refresh(new_business)
    return new_business

@router.get("/businesses", response_model=List[BusinessOut])
def get_businesses(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Check if the user is an admin
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view businesses")
    
    # Get all businesses
    businesses = db.query(models.Business).all()
    return businesses
# Update a business
@router.get("/businesses/{id}", response_model=BusinessOut)
def get_business(id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Check if the user is an admin
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this business")
    
    # Get the business
    business = db.query(models.Business).filter(models.Business.id == id).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    
    return business
#Delete a business
@router.delete("/businesses/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business(id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Admin mi kontrolü
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this business")
    
    # Business var mı kontrolü
    business = db.query(models.Business).filter(models.Business.id == id).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    # Fotoğraf klasörünü sil (eğer varsa)
    upload_folder = Path(f"app/uploads/business_photos/{id}")
    if upload_folder.exists() and upload_folder.is_dir():
        shutil.rmtree(upload_folder)

    # DB'den sil
    db.delete(business)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
# Upload a photo for a business
@router.post("/businesses/{id}/upload-photo")
def upload_business_photo(
    id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Yetki kontrolü
    business = db.query(models.Business).filter(models.Business.id == id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    if not current_user.is_admin and business.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Klasör oluştur
    upload_folder = Path(f"app/uploads/business_photos/{id}")
    upload_folder.mkdir(parents=True, exist_ok=True)

    # Dosyayı kaydet
    file_path = upload_folder / file.filename
    with open(file_path, "wb") as f:
        f.write(file.file.read())

    # BusinessImage tablosuna kayıt (varsayım)
    new_image = models.BusinessImage(business_id=id, path=str(file_path))
    db.add(new_image)
    db.commit()

    return {"status": "success", "photo_path": str(file_path)}

@router.post("/add-admin-temp")
def add_admin_temp(email: str, password: str, db: Session = Depends(get_db)):
    hashed_pw = utils.hash(password)

    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="User already exists.")

    new_user = models.User(
        email=email,
        password=hashed_pw,
        is_admin=True,
        is_active=True,
        is_verified=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    admin_entry = models.Admin(user_id=new_user.id)
    db.add(admin_entry)
    db.commit()

    return {"message": "Admin created", "user_id": new_user.id}

@router.get("/list_user_reservations", response_model=List[ReservationOut])
def list_user_reservations(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Yetki kontrolü
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can view user reservations")
    # Kullanıcı rezervasyonlarını getir
    reservations = db.query(models.Reservation).filter(models.Reservation.user_id == user_id).all()
    if not reservations:
        raise HTTPException(status_code=404, detail="No reservations found for this user")
    return reservations
@router.get("/list_user_comments", response_model=List[CommentOut])
def list_user_comments(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Yetki kontrolü
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can view user comments")
    # Kullanıcı yorumlarını getir
    comments = db.query(models.Comment).filter(models.Comment.user_id == user_id).all()
    if not comments:
        raise HTTPException(status_code=404, detail="No comments found for this user")

    return comments

@router.get("/activities", response_model=List[ActivityOut])
def list_all_activities(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can view activities")
    return db.query(models.Activity).order_by(models.Activity.created_at.desc()).all()
