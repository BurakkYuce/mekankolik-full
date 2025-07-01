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
    is_single_use: Optional[bool] = False

class CampaignCreate(CampaignBase):
    allowed_business_ids: Optional[List[int]] = None  # ilişkiyi yönetmek için      

# CampaignUsageOut'u aşağıda tanımladığımız için forward reference gerekir:
class CampaignOut(CampaignBase):
    id: int
    created_at: datetime
    assignments: List[CampaignAssignmentOut] = []
    allowed_business_ids: List[int] = []  # ✅ BU SATIRI EKLE

    class Config:
        from_attributes = True

# === CampaignUsage ===

class CampaignUsageBase(BaseModel):
    user_id: int
    assignment_id: int
    used_at: datetime
    business_id: int

class CampaignUsageCreate(CampaignUsageBase):
    business_id: int  # Kullanıcının hangi işletmede kampanyayı kullandığını belirtir


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
    rule_result: dict  # JSON olarak tutuluyor
    evaluated_at: datetime

    class Config:
        from_attributes = True
# RuleEvaluationLogOut, kampanya kurallarının değerlendirilmesi için kullanılır
