from geoalchemy2 import Geometry
from sqlalchemy import JSON, Column, Float, ForeignKey, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class User(Base):
    __tablename__ = "users"
    is_admin = Column(Boolean, default=False)
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)
    rating = Column(Float, nullable=True) 
    profile_photo = Column(String, nullable=True)  # Dosya yolu ya da URL
    phone_number = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    # İlişkiler
    admin_profile = relationship("Admin", back_populates="user", uselist=False, cascade="all, delete")
    businesses = relationship("Business", back_populates="owner", cascade="all, delete")
    my_comments = relationship("Comment", back_populates="user", cascade="all, delete")
    past_activities = relationship("Activity", back_populates="user", cascade="all, delete")
    used_campaigns = relationship("CampaignUsage", back_populates="user", cascade="all, delete")
    my_reservations = relationship("Reservation", back_populates="user", cascade="all, delete")
    assigned_campaigns = relationship("CampaignAssignment", back_populates="user", cascade="all, delete")

# İşletme türleri (örn. restoran, kafe, kuaför, vs.)
class BusinessCategory(str, enum.Enum):
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    HOTEL = "hotel"
    OTHER = "other" 

# İşletme durumu (admin onaylamış mı?)
class BusinessStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

class ReservationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    completed = "completed"
    confirmed = "confirmed"
    cancelled = "cancelled"

class Business(Base):
    __tablename__ = "business_profiles"
    working_hours = Column(String, nullable=True)  # Örn: "09:00-18:00"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    branch_code = Column(String, nullable=False, unique=True)  # İşletme sahibi için benzersiz kod
    password = Column(String, nullable=False)  # İşletme sahibi için ayrı parola
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    avg_price = Column(Integer, nullable=True)
    stars = Column(Float, nullable=True)
    category = Column(Enum(BusinessCategory), default=BusinessCategory.OTHER)
    status = Column(Enum(BusinessStatus, name="businessstatus"), default=BusinessStatus.pending)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    campaign_mappings = relationship("CampaignBusiness", back_populates="business", cascade="all, delete")

    # İlişkiler
    owner = relationship("User", back_populates="businesses")
    menus = relationship("Menu", back_populates="business", cascade="all, delete")
    comments = relationship("Comment", back_populates="business", cascade="all, delete")
    reservations = relationship("Reservation", back_populates="business", cascade="all, delete")
    tags = relationship("BusinessTag", back_populates="business", cascade="all, delete")
    images = relationship("BusinessImage", back_populates="business", cascade="all, delete")
    # ✅ Eklenmesi gereken ilişkiler:
    campaign_mappings = relationship("CampaignBusiness", back_populates="business", cascade="all, delete")
    campaign_usages = relationship("CampaignUsage", back_populates="business", cascade="all, delete")
    activities = relationship("Activity", back_populates="business", cascade="all, delete")

class BusinessTag(Base):
    __tablename__ = "business_tags"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    tag = Column(String, nullable=False)

    business = relationship("Business", back_populates="tags")

class BusinessImage(Base):
    __tablename__ = "business_images"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    path = Column(String, nullable=False)  # örn: "uploads/business/42/main.jpg"

    business = relationship("Business", back_populates="images")



class Menu(Base):
    __tablename__ = "menus"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    title = Column(String, nullable=False)  # Örn: "Kahvaltı", "Tatlılar", "Ana Yemekler"

    # İlişkiler
    business = relationship("Business", back_populates="menus")
    items = relationship("MenuItem", back_populates="menu", cascade="all, delete")

class MenuItem(Base):
    __tablename__ = "menu_items"
    id = Column(Integer, primary_key=True, index=True)
    menu_id = Column(Integer, ForeignKey("menus.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    image_path = Column(String, nullable=True)  # "uploads/menus/123.jpg" gibi dosya yolu

    # İlişkiler
    menu = relationship("Menu", back_populates="items")
    comments = relationship("Comment", back_populates="menu_item", cascade="all, delete")


class CampaignBusiness(Base):
    __tablename__ = "campaign_businesses"
    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)

    campaign = relationship("Campaign", back_populates="allowed_businesses")
    business = relationship("Business", back_populates="campaign_mappings")

class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="admin_profile")

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True)
    is_single_use = Column(Boolean, default=False)
    usage_duration_minutes = Column(Integer, default=10)  # Örn: 10 dk geçerli
    rule_type = Column(Enum("static", "dynamic", name="campaignruletype"), default="static")
    trigger_event = Column(Enum("none", "registration", "reservation", "purchase", name="triggereventtype"), default="none")
    criteria_json = Column(JSON, nullable=True)
    rules_description = Column(String, nullable=True)  # Admin için açıklama
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    allowed_businesses = relationship("CampaignBusiness", back_populates="campaign", cascade="all, delete")
    assignments = relationship("CampaignAssignment", back_populates="campaign", cascade="all, delete")


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=True)
    text = Column(String, nullable=False)
    rating = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # İlişkiler
    user = relationship("User", back_populates="my_comments")
    business = relationship("Business", back_populates="comments")
    menu_item = relationship("MenuItem", back_populates="comments")


class Activity(Base):
    __tablename__ = "activities"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    action_type = Column(String, nullable=False)  # Örn: "comment", "reservation", "campaign_usage"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    user = relationship("User", back_populates="past_activities")
    business = relationship("Business", back_populates="activities")

class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    reservation_time = Column(DateTime(timezone=True), nullable=False) 
    number_of_people = Column(Integer, nullable=False)
    special_requests = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(Enum(ReservationStatus, name="reservationstatus"), default=ReservationStatus.pending)

    user = relationship("User", back_populates="my_reservations")
    business = relationship("Business", back_populates="reservations")


class CampaignUsage(Base):
    __tablename__ = "campaign_usages"
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("campaign_assignments.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    used_at = Column(DateTime(timezone=True), server_default=func.now())
    business_id = Column(Integer, ForeignKey("business_profiles.id"), nullable=False)
    # İlişkiler
    assignment = relationship("CampaignAssignment", back_populates="usages")
    user = relationship("User", back_populates="used_campaigns")
    business = relationship("Business", back_populates="campaign_usages")


class CampaignAssignment(Base):
    __tablename__ = "campaign_assignments"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)

    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Kampanyanın kullanıcı için ömrü
    is_used = Column(Boolean, default=False)
    assigned_by_rule_engine = Column(Boolean, default=False)

    # QR ile oluşturulmuş bir token varsa onun süresi buradan izlenebilir
    qr_token = Column(String, nullable=True, unique=True)
    qr_expires_at = Column(DateTime(timezone=True), nullable=True)

    # İlişkiler
    user = relationship("User", back_populates="assigned_campaigns")
    campaign = relationship("Campaign", back_populates="assignments")
    usages = relationship("CampaignUsage", back_populates="assignment", cascade="all, delete")

class RuleEvaluationLog(Base):
    __tablename__ = "rule_evaluation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    rule_result = Column(JSON, nullable=False)  # Örn: {"min_reservations": true, "min_rating": false}
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler (opsiyonel, debug için)
    user = relationship("User")
    campaign = relationship("Campaign")


