import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pymongo.errors import DuplicateKeyError
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

# In-process lock to prevent concurrent coroutines from racing check-then-insert
_alert_eval_lock = asyncio.Lock()

async def evaluate_qr_exception_alert(db, now: datetime = None):
    async with _alert_eval_lock:
        if now is None:
            now = datetime.now(timezone.utc)

        window_start = now - timedelta(minutes=settings.ALERT_EXCEPTION_WINDOW_MINUTES)

        exception_statuses = ["NO_QR", "UNREADABLE_QR", "INVALID_QR", "AMBIGUOUS"]

        events = await db["events"].find({
            "timestamp": {"$gte": window_start, "$lte": now},
            "qr_status": {"$in": exception_statuses}
        }).to_list(length=1000)

        if len(events) >= settings.ALERT_EXCEPTION_THRESHOLD:
            existing_active_alert = await db["alerts"].find_one({
                "alert_type": "QR_EXCEPTION_SPIKE",
                "status": {"$in": ["OPEN", "ACKNOWLEDGED"]}
            })

            no_qr = sum(1 for e in events if e.get("qr_status") == "NO_QR")
            unreadable_qr = sum(1 for e in events if e.get("qr_status") == "UNREADABLE_QR")
            invalid_qr = sum(1 for e in events if e.get("qr_status") == "INVALID_QR")
            ambiguous_qr = sum(1 for e in events if e.get("qr_status") == "AMBIGUOUS")

            update_fields = {
                "exception_count": len(events),
                "no_qr_count": no_qr,
                "unreadable_qr_count": unreadable_qr,
                "invalid_qr_count": invalid_qr,
                "ambiguous_qr_count": ambiguous_qr,
                "window_end": now,
                "updated_at": now
            }

            if existing_active_alert:
                # Reusing the existing active alert, updating counts and window
                await db["alerts"].update_one(
                    {"_id": existing_active_alert["_id"]},
                    {"$set": update_fields}
                )
                return {"action": "updated", "alert_id": existing_active_alert.get("alert_id")}
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
                    "ambiguous_qr_count": ambiguous_qr,
                    "window_start": window_start,
                    "window_end": now,
                    "created_at": now,
                    "updated_at": now
                }
                try:
                    await db["alerts"].insert_one(new_alert)
                    return {"action": "created", "alert_id": alert_id}
                except DuplicateKeyError:
                    # In case of concurrent insert race across workers, update the winning active alert
                    winner = await db["alerts"].find_one({
                        "alert_type": "QR_EXCEPTION_SPIKE",
                        "status": {"$in": ["OPEN", "ACKNOWLEDGED"]}
                    })
                    if winner:
                        await db["alerts"].update_one(
                            {"_id": winner["_id"]},
                            {"$set": update_fields}
                        )
                        return {"action": "updated_on_collision", "alert_id": winner.get("alert_id")}
                    else:
                        # Competing active alert was resolved mid-race.
                        # Bounded single retry: insert a fresh active alert document.
                        retry_alert_id = str(uuid.uuid4())
                        retry_alert = {
                            "alert_id": retry_alert_id,
                            "alert_type": "QR_EXCEPTION_SPIKE",
                            "severity": "WARNING",
                            "status": "OPEN",
                            "exception_count": len(events),
                            "no_qr_count": no_qr,
                            "unreadable_qr_count": unreadable_qr,
                            "invalid_qr_count": invalid_qr,
                            "ambiguous_qr_count": ambiguous_qr,
                            "window_start": window_start,
                            "window_end": now,
                            "created_at": now,
                            "updated_at": now
                        }
                        try:
                            await db["alerts"].insert_one(retry_alert)
                            return {"action": "retry_created", "alert_id": retry_alert_id}
                        except DuplicateKeyError:
                            # Second collision occurred. Re-query for the new active alert.
                            second_winner = await db["alerts"].find_one({
                                "alert_type": "QR_EXCEPTION_SPIKE",
                                "status": {"$in": ["OPEN", "ACKNOWLEDGED"]}
                            })
                            if second_winner:
                                await db["alerts"].update_one(
                                    {"_id": second_winner["_id"]},
                                    {"$set": update_fields}
                                )
                                return {"action": "retry_updated", "alert_id": second_winner.get("alert_id")}
                            else:
                                logger.critical(
                                    "Alert collision persisted after single retry and no active alert found."
                                )
                                raise RuntimeError(
                                    "Alert evaluation failed: persistent collision on active alert state."
                                )
        return None
