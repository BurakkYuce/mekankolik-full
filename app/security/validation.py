# app/security/validation.py
import re
import html
import unicodedata
from typing import Optional, List, Any
from pydantic import BaseModel, Field, field_validator, EmailStr
from datetime import datetime
import ipaddress
import phonenumbers
from urllib.parse import urlparse

class ValidationUtils:
    """Comprehensive input validation utilities"""
    
    # Patterns for various validations
    SQL_INJECTION_PATTERNS = [
        r"(\b(union|select|insert|update|delete|drop|create|alter|exec|execute|script|javascript)\b)",
        r"(-{2,}|\/\*|\*\/|;|\|\||&&)",
        r"(xp_|sp_|@@)",
        r"('|(\\')|(\")|(\%27)|(\\\")|(\%22))",
    ]
    
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe",
        r"<object",
        r"<embed",
        r"<link",
        r"<meta"
    ]
    
    # Blocked email domains (disposable emails)
    BLOCKED_EMAIL_DOMAINS = [
        '10minutemail.com', 'tempmail.org', 'guerrillamail.com',
        'mailinator.com', 'throwaway.email', 'yopmail.com'
    ]
    
    @staticmethod
    def sanitize_string(
        text: str, 
        max_length: int = 1000, 
        allow_html: bool = False,
        strip_unicode: bool = False
    ) -> str:
        """Comprehensive string sanitization"""
        if not text:
            return ""
        
        # Remove null bytes and control characters
        text = text.replace('\x00', '')
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
        
        # Normalize unicode
        text = unicodedata.normalize('NFKC', text)
        
        # Strip unicode if requested
        if strip_unicode:
            text = text.encode('ascii', 'ignore').decode('ascii')
        
        # HTML escape if needed
        if not allow_html:
            text = html.escape(text)
        
        # Trim and limit length
        text = text.strip()[:max_length]
        
        return text
    
    @staticmethod
    def validate_sql_injection(text: str) -> bool:
        """Check for SQL injection patterns"""
        if not text:
            return True
        
        text_lower = text.lower()
        for pattern in ValidationUtils.SQL_INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return False
        return True
    
    @staticmethod
    def validate_xss(text: str) -> bool:
        """Check for XSS patterns"""
        if not text:
            return True
        
        for pattern in ValidationUtils.XSS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return False
        return True
    
    @staticmethod
    def validate_email_domain(email: str) -> bool:
        """Validate email domain against blocklist"""
        domain = email.split('@')[1].lower()
        return domain not in ValidationUtils.BLOCKED_EMAIL_DOMAINS
    
    @staticmethod
    def validate_phone_number(phone: str, region: str = "TR") -> Optional[str]:
        """Validate and format phone number"""
        try:
            parsed = phonenumbers.parse(phone, region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, 
                    phonenumbers.PhoneNumberFormat.E164
                )
        except:
            pass
        return None
    
    @staticmethod
    def validate_url(url: str, allowed_schemes: List[str] = ['http', 'https']) -> bool:
        """Validate URL format and scheme"""
        try:
            parsed = urlparse(url)
            return parsed.scheme in allowed_schemes and bool(parsed.netloc)
        except:
            return False
    
    @staticmethod
    def validate_ip_address(ip: str) -> bool:
        """Validate IP address format"""
        try:
            ipaddress.ip_address(ip)
            return True
        except:
            return False

# Enhanced Pydantic schemas with strong validation
class SecureUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        # Check blocked domains
        if not ValidationUtils.validate_email_domain(v):
            raise ValueError('Temporary email addresses not allowed')
        
        # Additional email validation
        if len(v) > 254:  # RFC 5321
            raise ValueError('Email too long')
        
        return v.lower()
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        # Length check
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        
        # Complexity requirements
        checks = {
            'uppercase': bool(re.search(r'[A-Z]', v)),
            'lowercase': bool(re.search(r'[a-z]', v)),
            'digit': bool(re.search(r'\d', v)),
            'special': bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', v))
        }
        
        if not all(checks.values()):
            missing = [k for k, v in checks.items() if not v]
            raise ValueError(f'Password must contain: {", ".join(missing)}')
        
        # Common password check
        common_passwords = ['password', '12345678', 'qwerty123', 'admin123']
        if v.lower() in common_passwords:
            raise ValueError('Password too common')
        
        return v
    
    @field_validator('phone_number')
    @classmethod
    def validate_phone(cls, v):
        if v:
            formatted = ValidationUtils.validate_phone_number(v)
            if not formatted:
                raise ValueError('Invalid phone number format')
            return formatted
        return v

class SecureCommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    rating: float = Field(..., ge=1.0, le=5.0)
    menu_item_id: Optional[int] = Field(None, gt=0)
    
    @field_validator('text')
    @classmethod
    def sanitize_and_validate_text(cls, v):
        # Sanitize
        v = ValidationUtils.sanitize_string(v, max_length=1000)
        
        # Check for SQL injection
        if not ValidationUtils.validate_sql_injection(v):
            raise ValueError('Invalid characters detected')
        
        # Check for XSS
        if not ValidationUtils.validate_xss(v):
            raise ValueError('Invalid content detected')
        
        # Check minimum content
        if len(v.strip()) < 10:
            raise ValueError('Comment too short (minimum 10 characters)')
        
        return v
    
    @field_validator('rating')
    @classmethod
    def validate_rating(cls, v):
        # Ensure rating is in 0.5 increments
        if (v * 2) % 1 != 0:
            raise ValueError('Rating must be in 0.5 increments')
        return v

class SecureBusinessCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    branch_code: str = Field(..., min_length=6, max_length=20)
    password: str = Field(..., min_length=8)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    phone: Optional[str] = None
    description: Optional[str] = Field(None, max_length=500)
    
    @field_validator('name')
    @classmethod
    def validate_business_name(cls, v):
        # Sanitize
        v = ValidationUtils.sanitize_string(v, max_length=100)
        
        # Business name pattern
        if not re.match(r'^[\w\s\-&.,\'()]+$', v):
            raise ValueError('Business name contains invalid characters')
        
        # No excessive spaces
        v = ' '.join(v.split())
        
        return v
    
    @field_validator('branch_code')
    @classmethod
    def validate_branch_code(cls, v):
        # Only alphanumeric and dash
        if not re.match(r'^[A-Za-z0-9\-]+$', v):
            raise ValueError('Branch code can only contain letters, numbers, and dashes')
        
        # No consecutive dashes
        if '--' in v:
            raise ValueError('Branch code cannot contain consecutive dashes')
        
        return v.upper()
    
    @field_validator('description')
    @classmethod
    def sanitize_description(cls, v):
        if v:
            return ValidationUtils.sanitize_string(v, max_length=500)
        return v

# Request body size validation
class RequestSizeValidator:
    """Validate request body size per endpoint"""
    
    # Size limits per content type
    LIMITS = {
        'application/json': 1 * 1024 * 1024,      # 1MB for JSON
        'multipart/form-data': 10 * 1024 * 1024,  # 10MB for file uploads
        'application/x-www-form-urlencoded': 64 * 1024  # 64KB for forms
    }
    
    @staticmethod
    def validate_content_length(content_type: str, content_length: int) -> bool:
        """Validate content length based on content type"""
        for ctype, limit in RequestSizeValidator.LIMITS.items():
            if ctype in content_type:
                return content_length <= limit
        
        # Default limit
        return content_length <= 1024 * 1024  # 1MB default

# Geographic validation
class LocationValidator:
    """Validate geographic coordinates and addresses"""
    
    @staticmethod
    def validate_coordinates(lat: float, lng: float) -> bool:
        """Validate latitude and longitude"""
        return -90 <= lat <= 90 and -180 <= lng <= 180
    
    @staticmethod
    def validate_turkish_postal_code(code: str) -> bool:
        """Validate Turkish postal code format"""
        return bool(re.match(r'^\d{5}$', code))

# Time-based validation
class TimeValidator:
    """Validate time-based inputs"""
    
    @staticmethod
    def validate_future_time(dt: datetime, min_future: int = 3600) -> bool:
        """Ensure datetime is in the future"""
        return (dt - datetime.now()).total_seconds() >= min_future
    
    @staticmethod
    def validate_business_hours(time_str: str) -> bool:
        """Validate business hours format (e.g., '09:00-18:00')"""
        pattern = r'^([01]?[0-9]|2[0-3]):[0-5][0-9]-([01]?[0-9]|2[0-3]):[0-5][0-9]$'
        return bool(re.match(pattern, time_str))