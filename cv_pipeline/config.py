from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    EDGE_NODE_API_KEY: str = "default_unsafe_key_for_dev"
    CAMERA_SOURCE: int = 0  # Default to 0, which is typically the integrated or primary USB webcam
    CAMERA_WIDTH: int = 1280
    CAMERA_HEIGHT: int = 720
    CAMERA_FPS: int = 30
    YOLO_MODEL_PATH: str = "yolov8n.pt"
    YOLO_CONFIDENCE_THRESHOLD: float = 0.5
    
    # Counting Line Configuration
    LINE_START_X: int = 0
    LINE_START_Y: int = 400
    LINE_END_X: int = 1280
    LINE_END_Y: int = 400
    TARGET_CLASS_NAME: str = "box"
    BACKEND_API_URL: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
