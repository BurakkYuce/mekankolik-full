from sqlalchemy.orm import Session
from app import models
from typing import Dict
from typing import List

def evaluate_campaign_rules(user: models.User, campaign: models.Campaign, db: Session) -> Dict[str, bool]:
    #Kullanicinin, kampanyanin kriterlerine uyup uymadiğini değerlendirir.
    results = {}
    criteria = campaign.criteria_json or {}

    # Kullanici puani
    if "min_rating" in criteria:
        results["min_rating"] = user.rating is not None and user.rating >= criteria["min_rating"]

    # Kullanicinin yaptiği rezervasyon sayisi
    if "min_reservations" in criteria:
        reservation_count = db.query(models.Reservation).filter_by(user_id=user.id).count()
        results["min_reservations"] = reservation_count >= criteria["min_reservations"]

    # Kullanicinin yaptiği yorum sayisi
    if "min_comments" in criteria:
        comment_count = db.query(models.Comment).filter_by(user_id=user.id).count()
        results["min_comments"] = comment_count >= criteria["min_comments"]

    # Ortalama harcama (şimdilik desteklenmiyor, örnek olarak false dönüyor)
    if "min_avg_spend" in criteria:
        results["min_avg_spend"] = False  # Uygulama desteklemiyorsa false dön
    return results

def assign_eligible_campaigns(user: models.User, db: Session):    
   # Kurallara göre kullaniciya uygun kampanyalari atar.
    campaigns = db.query(models.Campaign).filter(
        models.Campaign.rule_type == "dynamic",
        models.Campaign.is_active == True
    ).all()
    for campaign in campaigns:
        results = evaluate_campaign_rules(user, campaign, db)
        if all(results.values()):
            already_assigned = db.query(models.CampaignAssignment).filter_by(
                user_id=user.id,
                campaign_id=campaign.id
            ).first()

            if not already_assigned:
                assignment = models.CampaignAssignment(
                    user_id=user.id,
                    campaign_id=campaign.id,
                    assigned_by_rule_engine=True
                )
                db.add(assignment)
                log = models.RuleEvaluationLog(
                    user_id=user.id,
                    campaign_id=campaign.id,
                    rule_result=results
                )
                db.add(log)
    db.commit()
