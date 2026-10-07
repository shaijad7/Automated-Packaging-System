from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class AlertBase(BaseModel):
    alert_id: str
    alert_type: str = "QR_EXCEPTION_SPIKE"
    severity: str = "WARNING"
    status: str = "OPEN"
    exception_count: int
    no_qr_count: int
    unreadable_qr_count: int
    invalid_qr_count: int
    window_start: datetime
    window_end: datetime
    created_at: datetime
    updated_at: datetime
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    resolution_reason: Optional[str] = None

class AlertInDB(AlertBase):
    pass
