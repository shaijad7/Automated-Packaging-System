from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent / ".env"

class Settings(BaseSettings):
    EDGE_NODE_API_KEY: str
    CAMERA_SOURCE: int = 0  # Default to 0, which is typically the integrated or primary USB webcam
    CAMERA_WIDTH: int = 1280
    CAMERA_HEIGHT: int = 720
    CAMERA_FPS: int = 30
    YOLO_MODEL_PATH: str = "models/best.pt"
    YOLO_CONFIDENCE_THRESHOLD: float = 0.5
    
    # Counting Line Configuration
    LINE_START_X: int = 0
    LINE_START_Y: int = 400
    LINE_END_X: int = 1280
    LINE_END_Y: int = 400
    TARGET_CLASS_NAME: str = "box"
    BACKEND_API_URL: str = "http://localhost:8000"

    # Diagnostics Configuration
    ENABLE_DIAGNOSTICS: bool = False
    DIAGNOSTICS_DIR: str = "diagnostics_dumps"
    MAX_DIAGNOSTIC_FRAMES: int = 20

    # Spool Configuration
    EVENT_SPOOL_PATH: str = "data/event_spool.db"
    EVENT_SPOOL_MAX_SIZE: int = 10000

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("EDGE_NODE_API_KEY")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("EDGE_NODE_API_KEY is required and cannot be empty or whitespace.")
        return v.strip()

settings = Settings()
