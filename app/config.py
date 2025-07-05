# app/config.py - Secure configuration with all settings
from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache
import secrets

class Settings(BaseSettings):
    # === Database Configuration ===
    database_hostname: str
    database_port: str = "5432"
    database_name: str
    database_username: str
    database_password: str
    database_ssl_mode: str = "require"  # Force SSL in production
    
    # === JWT Configuration ===
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30  # 30 minutes
    refresh_token_expire_days: int = 7
    
    # === Environment Configuration ===
    environment: str = "development"  # development, staging, production
    debug: bool = False
    
    # === Security Configuration ===
    # Admin
    admin_ip_whitelist: str = "127.0.0.1,192.168.1.0/24"
    super_admin_api_key: str
    
    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    
    # File Upload
    max_file_size: int = 5242880  # 5MB
    upload_dir: str = "app/uploads/"
    allowed_file_types: str = "image/jpeg,image/png,image/webp"
    
    # Session
    session_secret_key: Optional[str] = None
    session_max_age: int = 3600  # 1 hour
    
    # === External Services ===
    redis_url: Optional[str] = None
    sentry_dsn: Optional[str] = None
    
    # === Email Configuration ===
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    email_from: str = "noreply@yourdomain.com"
    
    # === Monitoring ===
    monitoring_api_key: str
    enable_metrics: bool = True
    enable_tracing: bool = False
    
    # === CORS Configuration ===
    cors_origins: str = "http://localhost:3000,https://yourdomain.com"
    allowed_hosts: str = "localhost,127.0.0.1,yourdomain.com"
    
    # === Password Policy ===
    password_min_length: int = 8
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_numbers: bool = True
    password_require_special: bool = True
    password_history_count: int = 5  # Remember last 5 passwords
    password_expiry_days: int = 90
    
    # === Login Security ===
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30
    require_2fa: bool = False
    
    # === Audit Configuration ===
    enable_audit_log: bool = True
    audit_log_retention_days: int = 90
    
    # === Backup Configuration ===
    backup_enabled: bool = True
    backup_schedule: str = "0 2 * * *"  # 2 AM daily
    backup_retention_days: int = 30
    backup_encryption_key: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    # === Helper Methods ===
    
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    def is_development(self) -> bool:
        return self.environment.lower() == "development"
    
    def is_staging(self) -> bool:
        return self.environment.lower() == "staging"
    
    def get_allowed_origins(self) -> List[str]:
        """Get CORS allowed origins as list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    def get_allowed_hosts(self) -> List[str]:
        """Get allowed hosts as list"""
        return [host.strip() for host in self.allowed_hosts.split(",")]
    
    def get_allowed_file_types(self) -> List[str]:
        """Get allowed file types as list"""
        return [ftype.strip() for ftype in self.allowed_file_types.split(",")]
    
    def get_admin_ips(self) -> List[str]:
        """Get admin IP whitelist as list"""
        return [ip.strip() for ip in self.admin_ip_whitelist.split(",")]
    
    def get_database_url(self) -> str:
        """Get database URL with SSL if production"""
        base_url = f"postgresql://{self.database_username}:{self.database_password}@{self.database_hostname}:{self.database_port}/{self.database_name}"
        
        if self.is_production():
            return f"{base_url}?sslmode={self.database_ssl_mode}"
        return base_url
    
    def validate_settings(self):
        """Validate critical settings"""
        errors = []
        
        # Check secret key strength
        if len(self.secret_key) < 32:
            errors.append("SECRET_KEY must be at least 32 characters")
        
        # Check default passwords
        if self.database_password in ["password", "admin", "123456", "a"]:
            errors.append("Database password is too weak")
        
        # Production checks
        if self.is_production():
            if self.debug:
                errors.append("DEBUG must be False in production")
            
            if not self.database_ssl_mode == "require":
                errors.append("Database SSL must be required in production")
            
            if not self.redis_url:
                errors.append("Redis is required for production (rate limiting)")
            
            if not self.backup_encryption_key:
                errors.append("Backup encryption key required in production")
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
    
    def generate_secure_keys(self):
        """Generate secure random keys for first setup"""
        return {
            "secret_key": secrets.token_urlsafe(32),
            "session_secret_key": secrets.token_urlsafe(32),
            "super_admin_api_key": secrets.token_urlsafe(32),
            "monitoring_api_key": secrets.token_urlsafe(24),
            "backup_encryption_key": secrets.token_urlsafe(32)
        }

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    settings = Settings()
    
    # Auto-generate session key if not set
    if not settings.session_secret_key:
        settings.session_secret_key = secrets.token_urlsafe(32)
    
    # Validate in production
    if settings.is_production():
        settings.validate_settings()
    
    return settings

settings = get_settings()

# === Environment File Template (.env.example) ===
