from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Supabase Configuration
    supabase_url: str
    supabase_key: str
    
    # JWT Configuration
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Application Configuration
    app_name: str = "Conduit"
    app_version: str = "1.0.0"
    debug: bool = True
    
    # CORS Configuration
    allowed_origins: str = "http://localhost:3000,http://localhost:8080"
    
    # WebRTC Configuration
    webrtc_stun_server: str = "stun:stun.l.google.com:19302"
    
    fcm_server_key: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]


settings = Settings()
