from pathlib import Path
from pydantic_settings import BaseSettings

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"

def parse_cors_origins(origins_val: str | list[str] | None) -> list[str]:
    """
    Parses comma-separated CORS origins into a sanitized list of strings.
    Trims whitespace around each origin and ignores empty entries.
    """
    if not origins_val:
        return []
    if isinstance(origins_val, list):
        return [o.strip() for o in origins_val if isinstance(o, str) and o.strip()]
    return [origin.strip() for origin in origins_val.split(",") if origin.strip()]

class Settings(BaseSettings):
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "smart_inventory"
    JWT_SECRET_KEY: str
    API_CORS_ORIGINS: str = "http://localhost:3000"
    EDGE_NODE_API_KEY: str
    ALERT_EXCEPTION_THRESHOLD: int = 5
    ALERT_EXCEPTION_WINDOW_MINUTES: int = 10
    
    @property
    def cors_origins(self) -> list[str]:
        return parse_cors_origins(self.API_CORS_ORIGINS)

    class Config:
        env_file = str(_ENV_FILE) if _ENV_FILE.exists() else ".env"
        extra = "ignore"

settings = Settings()
