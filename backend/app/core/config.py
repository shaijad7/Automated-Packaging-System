from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGODB_URI: str
    JWT_SECRET_KEY: str
    API_CORS_ORIGINS: str = "http://localhost:3000"
    EDGE_NODE_API_KEY: str
    ALERT_EXCEPTION_THRESHOLD: int = 5
    ALERT_EXCEPTION_WINDOW_MINUTES: int = 10
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
