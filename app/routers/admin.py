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
import uuid
import mimetypes
from PIL import Image
import os


router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)
# admin.py - Düzeltilmiş business creation

@router.post("/create", status_code=status.HTTP_201_CREATED, response_model=BusinessOut)
def create_business(
    business: BusinessCreate, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    """"""
    # Admin kontrolü
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # ✅ Input validation
    if not business.name or len(business.name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Business name too short")
    
    if not business.email:
        raise HTTPException(status_code=400, detail="Business email required")
    
    # ✅ Business name kontrolü (case insensitive)
    existing_business = db.query(models.Business).filter(
        models.Business.name.ilike(f"%{business.name.strip()}%")
    ).first()
    if existing_business:
        raise HTTPException(status_code=400, detail="Business with similar name already exists")
    
    # ✅ Email kontrolü
    existing_email = db.query(models.Business).filter(
        models.Business.email == business.email.lower()
    ).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Business email already in use")
    
    # ✅ Branch code kontrolü
    existing_branch = db.query(models.Business).filter(
        models.Business.branch_code == business.branch_code
    ).first()
    if existing_branch:
        raise HTTPException(status_code=400, detail="Branch code already in use")

    try:
        # Şifreyi hashle
        hashed_password = utils.hash(business.password)

        # ✅ Hedef kullanıcıyı belirle
        target_user_id = business.user_id  # Schema'dan gelen user_id'yi kullan
        
        # Hedef kullanıcı var mı kontrol et
        target_user = db.query(models.User).filter(models.User.id == target_user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="Target user not found")

        # Business data hazırla
        business_data = business.dict(exclude={"user_id", "password"})
        business_data["password"] = hashed_password
        business_data["email"] = business.email.lower()  # Email'i normalize et
        business_data["name"] = business.name.strip()    # Name'i temizle

        # Yeni business oluştur
        new_business = models.Business(**business_data, user_id=target_user_id)
        db.add(new_business)
        db.commit()
        db.refresh(new_business)
        
        # ✅ Admin aktivitesini logla
        utils.log_activity(db, current_user.id, new_business.id, "admin_business_create")
        
        return new_business

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create business")

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
# Güvenli file upload endpoint'i
@router.post("/businesses/{id}/upload-photo")
def upload_business_photo_secure(
    id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Yetki kontrolü
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    business = db.query(models.Business).filter(models.Business.id == id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # ✅ File validation
    # 1. Dosya boyutu kontrolü (5MB max)
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    file.file.seek(0, 2)  # End of file
    file_size = file.file.tell()
    file.file.seek(0)  # Reset
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")
    
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # 2. Dosya tipi kontrolü
    ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
    ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']
    
    # Content-Type kontrolü
    content_type = file.content_type
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type. Only JPEG, PNG, WebP allowed")
    
    # Dosya uzantısı kontrolü
    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file extension")

    # 3. Güvenli dosya adı oluştur (path traversal koruması)
    secure_filename = f"{uuid.uuid4().hex}_{id}{file_extension}"
    
    # 4. Upload klasörü oluştur
    upload_folder = Path(f"app/uploads/business_photos/{id}")
    upload_folder.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_folder / secure_filename

    try:
        # 5. Dosyayı geçici olarak kaydet
        temp_path = upload_folder / f"temp_{secure_filename}"
        with open(temp_path, "wb") as temp_file:
            temp_file.write(file.file.read())

        # 6. PIL ile resim doğrulaması (zararlı dosya kontrolü)
        try:
            with Image.open(temp_path) as img:
                # Resim boyutu kontrolü
                max_dimension = 2048
                if img.width > max_dimension or img.height > max_dimension:
                    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                
                # EXIF verilerini temizle ve güvenli formatta kaydet
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                img.save(file_path, 'JPEG', quality=85, optimize=True)
                
        except Exception as img_error:
            # Geçici dosyayı temizle
            if temp_path.exists():
                temp_path.unlink()
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        # 7. Geçici dosyayı temizle
        if temp_path.exists():
            temp_path.unlink()

        # 8. Database'e kaydet
        new_image = models.BusinessImage(business_id=id, path=str(file_path))
        db.add(new_image)
        db.commit()

        # 9. Admin aktivitesini logla
        utils.log_activity(db, current_user.id, id, "admin_photo_upload")
        
        return {
            "status": "success", 
            "photo_path": str(file_path),
            "filename": secure_filename
        }

    except HTTPException:
        raise
    except Exception as e:
        # Hata durumunda dosyaları temizle
        for path in [file_path, temp_path]:
            if path.exists():
                path.unlink()
        raise HTTPException(status_code=500, detail="Upload failed")
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
