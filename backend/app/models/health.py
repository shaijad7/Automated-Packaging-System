from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field

HealthStatusLiteral = Literal["UP", "DOWN", "DEGRADED", "UNKNOWN"]

class EdgeHeartbeatPayload(BaseModel):
    timestamp: datetime
    camera: HealthStatusLiteral
    camera_details: Optional[str] = Field(default=None, max_length=200)
    model: HealthStatusLiteral
    model_details: Optional[str] = Field(default=None, max_length=200)
    fps: Optional[float] = Field(default=None, ge=0.0, le=240.0)
    last_frame_timestamp: Optional[str] = Field(default=None, max_length=50)
    last_inference_timestamp: Optional[str] = Field(default=None, max_length=50)

    class Config:
        extra = "forbid"
