from sqlalchemy.orm import Session
from app import models
from typing import Dict
from datetime import datetime

def evaluate_campaign_rules(user: models.User, campaign: models.Campaign, db: Session) -> Dict[str, bool]:
    """Kullanıcının kampanya kriterlerine uygunluğunu değerlendirir"""
    results = {}
    criteria = campaign.criteria_json or {}
    
    # Assignment'ı bul
    assignment = db.query(models.CampaignAssignment).filter_by(
        user_id=user.id, 
        campaign_id=campaign.id
    ).first()
    
    if not assignment:
        # Assignment yoksa tüm kriterler False
        for key in criteria.keys():
            results[key] = False
        return results
    
    # Progress kaydını bul
    progress = db.query(models.CampaignProgress).filter_by(
        assignment_id=assignment.id
    ).first()
    
    if not progress:
        # Progress yoksa tüm kriterler False
        for key in criteria.keys():
            results[key] = False
        return results
    
    # ✅ Kampanya sonrası kriterler
    if "min_comments_after_assignment" in criteria:
        results["min_comments_after_assignment"] = progress.comments_made >= criteria["min_comments_after_assignment"]
    
    if "min_reservations_after_assignment" in criteria:
        results["min_reservations_after_assignment"] = progress.reservations_made >= criteria["min_reservations_after_assignment"]
    
    if "min_businesses_visited" in criteria:
        results["min_businesses_visited"] = progress.businesses_visited >= criteria["min_businesses_visited"]
    
    if "min_spend_after_assignment" in criteria:
        results["min_spend_after_assignment"] = progress.total_spend >= criteria["min_spend_after_assignment"]
    
    # ✅ Genel kriterler (assignment öncesi + sonrası)
    if "min_rating" in criteria:
        results["min_rating"] = user.rating is not None and user.rating >= criteria["min_rating"]
    
    # Eski kriterler (geriye uyumluluk için)
    if "min_reservations" in criteria:
        reservation_count = db.query(models.Reservation).filter_by(user_id=user.id).count()
        results["min_reservations"] = reservation_count >= criteria["min_reservations"]

    if "min_comments" in criteria:
        comment_count = db.query(models.Comment).filter_by(user_id=user.id).count()
        results["min_comments"] = comment_count >= criteria["min_comments"]
    
    return results

def assign_eligible_campaigns(user: models.User, db: Session):
    """Kurallara göre kullanıcıya uygun kampanyaları atar"""
    campaigns = db.query(models.Campaign).filter(
        models.Campaign.rule_type == "dynamic",
        models.Campaign.is_active == True
    ).all()
    
    for campaign in campaigns:
        already_assigned = db.query(models.CampaignAssignment).filter_by(
            user_id=user.id,
            campaign_id=campaign.id
        ).first()
        
        if not already_assigned:
            # Assignment oluştur
            assignment = models.CampaignAssignment(
                user_id=user.id,
                campaign_id=campaign.id,
                assigned_by_rule_engine=True
            )
            db.add(assignment)
            db.flush()  # ID almak için
            
            # ✅ Progress kaydı oluştur
            progress = models.CampaignProgress(
                assignment_id=assignment.id,
                user_id=user.id,
                campaign_id=campaign.id
            )
            db.add(progress)
            
            # Log oluştur
            log = models.RuleEvaluationLog(
                user_id=user.id,
                campaign_id=campaign.id,
                rule_result={}  # İlk atamada boş
            )
            db.add(log)
    
    db.commit()

def create_progress_for_assignment(assignment: models.CampaignAssignment, db: Session):
    """Yeni assignment için progress kaydı oluşturur"""
    existing_progress = db.query(models.CampaignProgress).filter_by(
        assignment_id=assignment.id
    ).first()
    
    if not existing_progress:
        progress = models.CampaignProgress(
            assignment_id=assignment.id,
            user_id=assignment.user_id,
            campaign_id=assignment.campaign_id
        )
        db.add(progress)
        db.commit()
        return progress
    return existing_progress
