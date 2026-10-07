from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class EventCreate(BaseModel):
    event_id: str
    timestamp: datetime
    track_id: int
    qr_status: str
    qr_payload: Optional[str] = None
    count_direction: Optional[str] = None

class EventInDB(EventCreate):
    sku: Optional[str] = None
    status: str
