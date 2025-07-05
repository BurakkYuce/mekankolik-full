from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Database settings
    database_hostname: str
    database_port: str
    database_name: str
    database_username: str
    database_password: str

    # JWT settings
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int

    # ✅ Yeni güvenlik alanları ekle
    # File upload settings
    max_file_size: int = 5242880  
    upload_dir: str = "app/uploads/"
    
    # Admin security settings
    admin_ip_whitelist: str = "127.0.0.1,192.168.1.0/24"
    
    # Environment settings
    environment: str = "development"
    debug: bool = False

    class Config:
        env_file = ".env"
        
    # ✅ Helper methods
    def get_allowed_admin_ips(self) -> List[str]:
        """Admin IP whitelist'ini list olarak döndür"""
        return [ip.strip() for ip in self.admin_ip_whitelist.split(",")]
    
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

settings = Settings()