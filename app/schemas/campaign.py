
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# === Campaign ===

class CampaignAssignmentOut(BaseModel):
    id: int
    user_id: int
    campaign_id: int
    assigned_at: datetime
    expires_at: Optional[datetime]
    is_used: bool
    qr_token: Optional[str]
    qr_expires_at: Optional[datetime]

    class Config:
        from_attributes = True

class CampaignBase(BaseModel):
    title: str
    description: Optional[str] = None
    start_date: datetime
    end_date: datetime
    is_active: Optional[bool] = True
    # ✅ Tüm kampanya alanları
    is_single_use: Optional[bool] = False
    usage_duration_minutes: Optional[int] = 10
    rule_type: Optional[str] = "static"  # "static" veya "dynamic"
    trigger_event: Optional[str] = "none"  # "none", "registration", "reservation", "purchase"
    criteria_json: Optional[dict] = None
    rules_description: Optional[str] = None

class CampaignCreate(CampaignBase):
    allowed_business_ids: Optional[List[int]] = None

class CampaignOut(CampaignBase):
    id: int
    created_at: datetime
    assignments: List[CampaignAssignmentOut] = []
    allowed_business_ids: List[int] = []

    class Config:
        from_attributes = True

# === CampaignUsage ===

class CampaignUsageBase(BaseModel):
    user_id: int
    assignment_id: int
    used_at: datetime
    business_id: int

class CampaignUsageCreate(CampaignUsageBase):
    business_id: int

class CampaignUsageOut(CampaignUsageBase):
    id: int
    campaign_id: int

    class Config:
        from_attributes = True

# Forward reference çözümü
CampaignOut.model_rebuild()

class RuleEvaluationLogOut(BaseModel):
    id: int
    user_id: int
    campaign_id: int
    rule_result: dict
    evaluated_at: datetime

    class Config:
        from_attributes = True