from .. import models, utils
from ..schemas.comment import CommentCreate, CommentOut, CommentBase
from fastapi import Depends, FastAPI, Response, status, HTTPException, APIRouter, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..oauth2 import get_current_user
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/comment",
    tags=["Comment"]
)

@router.post("/{id}", response_model=CommentOut)
def create_comment(
    id: int, 
    comment: CommentCreate, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    """Yorum oluşturma endpoint'i"""
    
    try:
        # ✅ Input validation
        if id <= 0:
            raise HTTPException(status_code=400, detail="Invalid business ID")
        
        if not comment.text or len(comment.text.strip()) < 1:
            raise HTTPException(status_code=400, detail="Comment text cannot be empty")
        
        if len(comment.text) > 1000:  # Character limit
            raise HTTPException(status_code=400, detail="Comment too long (max 1000 characters)")
        
        if comment.rating < 1.0 or comment.rating > 5.0:
            raise HTTPException(status_code=400, detail="Rating must be between 1.0 and 5.0")

        # Business kontrolü
        business = db.query(models.Business).filter(models.Business.id == id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")


        # Kullanıcı daha önce yorum yapmış mı kontrolü
        existing_comment = db.query(models.Comment).filter(
            models.Comment.business_id == id, 
            models.Comment.user_id == current_user.id
        ).first()
        
        if existing_comment:
            raise HTTPException(status_code=400, detail="You have already commented on this business")

        # ✅ Menu item kontrolü (eğer belirtilmişse)
        menu_item_id = None
        if comment.menu_item_id and comment.menu_item_id != 0:
            menu_item = db.query(models.MenuItem).filter(
                models.MenuItem.id == comment.menu_item_id
            ).first()
            if not menu_item:
                raise HTTPException(status_code=404, detail="Menu item not found")
            # Menu item bu business'a ait mi kontrol et
            if menu_item.menu.business_id != id:
                raise HTTPException(status_code=400, detail="Menu item does not belong to this business")
            menu_item_id = comment.menu_item_id

        # ✅ Yeni comment oluştur
        new_comment = models.Comment(
            text=comment.text.strip(),  # Whitespace temizle
            rating=comment.rating,
            business_id=id,  # URL'den gelen business ID
            user_id=current_user.id,
            menu_item_id=menu_item_id
        )

        db.add(new_comment)
        db.commit()
        db.refresh(new_comment)

        # ✅ Campaign progress güncelle
        utils.update_campaign_progress(db, current_user.id, "comment", business_id=id)
        
        # ✅ Activity logla - DOĞRU business_id kullanımı
        utils.log_activity(db, current_user.id, id, "comment")  # id = business_id

        # ✅ Business rating'i güncelle (opsiyonel - background task yapılabilir)
        update_business_rating(db, id)

        logger.info(f"Comment created - User: {current_user.id} - Business: {id} - Rating: {comment.rating}")
        
        return new_comment

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating comment: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create comment")

@router.get("/{id}", response_model=List[CommentOut])
def get_comments(
    id: int, 
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of comments to skip"),
    limit: int = Query(50, ge=1, le=100, description="Number of comments to return"),
    min_rating: Optional[float] = Query(None, ge=1.0, le=5.0, description="Minimum rating filter"),
    sort_by: str = Query("newest", regex="^(newest|oldest|rating_high|rating_low)$", description="Sort order")
):
    """İşletme yorumlarını listeleme (pagination ve filtering ile)"""
    
    try:
        # ✅ Input validation
        if id <= 0:
            raise HTTPException(status_code=400, detail="Invalid business ID")

        # Business kontrolü
        business = db.query(models.Business).filter(models.Business.id == id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        # ✅ Base query
        query = db.query(models.Comment).filter(models.Comment.business_id == id)

        # ✅ Rating filter
        if min_rating:
            query = query.filter(models.Comment.rating >= min_rating)

        # ✅ Sorting
        if sort_by == "newest":
            query = query.order_by(models.Comment.created_at.desc())
        elif sort_by == "oldest":
            query = query.order_by(models.Comment.created_at.asc())
        elif sort_by == "rating_high":
            query = query.order_by(models.Comment.rating.desc())
        elif sort_by == "rating_low":
            query = query.order_by(models.Comment.rating.asc())

        # ✅ Pagination
        comments = query.offset(skip).limit(limit).all()
        
        return comments

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching comments: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch comments")

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    id: int, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    """Yorum silme (sadece yorum sahibi veya admin)"""
    
    try:
        # ✅ Input validation
        if id <= 0:
            raise HTTPException(status_code=400, detail="Invalid comment ID")

        # Comment kontrolü - sadece kendi yorumunu silebilir
        comment = db.query(models.Comment).filter(models.Comment.id == id).first()
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        # ✅ Yetki kontrolü - comment sahibi veya admin
        if comment.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Not authorized to delete this comment")

        # ✅ Comment bilgilerini kaydet (log için)
        business_id = comment.business_id
        comment_user_id = comment.user_id
        comment_rating = comment.rating

        # Comment'i sil
        db.delete(comment)
        db.commit()

        # ✅ Business rating'i güncelle
        update_business_rating(db, business_id)

        # ✅ Activity logla
        action_type = "admin_delete_comment" if current_user.is_admin and comment_user_id != current_user.id else "delete_comment"
        utils.log_activity(db, current_user.id, business_id, action_type)

        logger.info(f"Comment deleted - ID: {id} - User: {current_user.id} - Business: {business_id}")
        
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting comment: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete comment")

# ✅ Helper function - Business rating güncelleme
def update_business_rating(db: Session, business_id: int):
    """Business'ın ortalama rating'ini güncelle"""
    try:
        # Business'ın tüm comment'lerinin ortalamasını al
        avg_rating = db.query(
            db.func.avg(models.Comment.rating)
        ).filter(
            models.Comment.business_id == business_id
        ).scalar()

        # Business'ı güncelle
        business = db.query(models.Business).filter(models.Business.id == business_id).first()
        if business:
            business.stars = round(avg_rating, 2) if avg_rating else None
            db.commit()

    except Exception as e:
        logger.error(f"Error updating business rating: {str(e)}")
        db.rollback()

# ✅ Bonus: Comment istatistikleri endpoint'i
@router.get("/{id}/stats")
def get_comment_stats(
    id: int,
    db: Session = Depends(get_db)
):
    """İşletme comment istatistikleri"""
    
    try:
        if id <= 0:
            raise HTTPException(status_code=400, detail="Invalid business ID")

        # Business kontrolü
        business = db.query(models.Business).filter(models.Business.id == id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        # İstatistikleri hesapla
        total_comments = db.query(models.Comment).filter(models.Comment.business_id == id).count()
        
        if total_comments == 0:
            return {
                "total_comments": 0,
                "average_rating": None,
                "rating_distribution": {}
            }

        avg_rating = db.query(
            db.func.avg(models.Comment.rating)
        ).filter(
            models.Comment.business_id == id
        ).scalar()

        # Rating dağılımı
        rating_dist = {}
        for rating in [1, 2, 3, 4, 5]:
            count = db.query(models.Comment).filter(
                models.Comment.business_id == id,
                models.Comment.rating >= rating,
                models.Comment.rating < rating + 1
            ).count()
            rating_dist[f"{rating}_star"] = count

        return {
            "total_comments": total_comments,
            "average_rating": round(avg_rating, 2) if avg_rating else None,
            "rating_distribution": rating_dist
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching comment stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")