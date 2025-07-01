from .. import models, utils
from ..schemas.comment import CommentCreate, CommentOut, CommentBase
from fastapi import Depends, FastAPI, Response, status, HTTPException, APIRouter
from sqlalchemy.orm import Session
from ..database import get_db
from ..oauth2 import get_current_user
from typing import List

router = APIRouter(
    prefix="/comment",
    tags=["Comment"]
    )

@router.post("/{id}",response_model=CommentOut) #yorum oluşturma
def create_comment(id: int, comment: CommentCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Check if the business exists
    business = db.query(models.Business).filter(models.Business.id == id).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    # Check if the user has already commented on this business
    existing_comment = db.query(models.Comment).filter(models.Comment.business_id == id, models.Comment.user_id == current_user.id).first()
    if existing_comment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already commented on this business")

    
    menu_item_id = comment.menu_item_id if comment.menu_item_id != 0 else None

    # Create a new comment
    new_comment = models.Comment(
        text=comment.text,
        rating=comment.rating,
        business_id=id,
        user_id=current_user.id,
        menu_item_id=menu_item_id
    )

    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    utils.log_activity(db, current_user.id, comment.business_id, "comment")

    return new_comment

@router.get("/{id}", response_model=List[CommentOut])#yorumları listeleme
def get_comments(id: int, db: Session = Depends(get_db)):
    # Check if the business exists
    business = db.query(models.Business).filter(models.Business.id == id).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    # Get all comments for the business
    comments = db.query(models.Comment).filter(models.Comment.business_id == id).all()
    return comments

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)#yorum silme
def delete_comment(id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Check if the comment exists
    comment = db.query(models.Comment).filter(models.Comment.id == id, models.Comment.user_id == current_user.id).first()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    # Delete the comment
    db.delete(comment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


