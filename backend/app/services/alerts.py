import uuid
from datetime import datetime, timezone, timedelta
from app.core.config import settings

async def evaluate_qr_exception_alert(db, now: datetime = None):
    if now is None:
        now = datetime.now(timezone.utc)
    
    window_start = now - timedelta(minutes=settings.ALERT_EXCEPTION_WINDOW_MINUTES)
    
    exception_statuses = ["NO_QR", "UNREADABLE_QR", "INVALID_QR"]
    
    events = await db["events"].find({
        "timestamp": {"$gte": window_start, "$lte": now},
        "qr_status": {"$in": exception_statuses}
    }).to_list(length=1000)
    
    if len(events) >= settings.ALERT_EXCEPTION_THRESHOLD:
        existing_open_alert = await db["alerts"].find_one({
            "alert_type": "QR_EXCEPTION_SPIKE",
            "status": "OPEN"
        })
        
        no_qr = sum(1 for e in events if e.get("qr_status") == "NO_QR")
        unreadable_qr = sum(1 for e in events if e.get("qr_status") == "UNREADABLE_QR")
        invalid_qr = sum(1 for e in events if e.get("qr_status") == "INVALID_QR")
        
        if existing_open_alert:
            # Reusing the existing OPEN alert, updating counts and window
            await db["alerts"].update_one(
                {"_id": existing_open_alert["_id"]},
                {"$set": {
                    "exception_count": len(events),
                    "no_qr_count": no_qr,
                    "unreadable_qr_count": unreadable_qr,
                    "invalid_qr_count": invalid_qr,
                    "window_end": now,
                    "updated_at": now
                }}
            )
        else:
            alert_id = str(uuid.uuid4())
            new_alert = {
                "alert_id": alert_id,
                "alert_type": "QR_EXCEPTION_SPIKE",
                "severity": "WARNING",
                "status": "OPEN",
                "exception_count": len(events),
                "no_qr_count": no_qr,
                "unreadable_qr_count": unreadable_qr,
                "invalid_qr_count": invalid_qr,
                "window_start": window_start,
                "window_end": now,
                "created_at": now,
                "updated_at": now
            }
            await db["alerts"].insert_one(new_alert)
