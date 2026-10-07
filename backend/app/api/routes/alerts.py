from fastapi import APIRouter, Depends, HTTPException, Query
from app.models.alert import AlertInDB
from app.models.user import TokenData
from app.api.deps import get_current_user
from app.db.mongodb import get_db
import pymongo
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

@router.get("/", response_model=list[AlertInDB])
async def list_alerts(
    status: str = Query("ALL", description="Filter by status: ALL, OPEN, ACKNOWLEDGED, RESOLVED"),
    limit: int = Query(50, ge=1, le=100),
    current_user: TokenData = Depends(get_current_user)
):
    db = get_db()
    query = {}
    if status != "ALL":
        query["status"] = status
        
    alerts = await db["alerts"].find(query).sort("created_at", pymongo.DESCENDING).limit(limit).to_list(limit)
    return [AlertInDB(**a) for a in alerts]

@router.get("/{alert_id}", response_model=AlertInDB)
async def get_alert(alert_id: str, current_user: TokenData = Depends(get_current_user)):
    db = get_db()
    alert = await db["alerts"].find_one({"alert_id": alert_id})
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertInDB(**alert)

@router.patch("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, current_user: TokenData = Depends(get_current_user)):
    db = get_db()
    alert = await db["alerts"].find_one({"alert_id": alert_id})
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
        
    if alert["status"] != "OPEN":
        raise HTTPException(status_code=400, detail="Only OPEN alerts can be acknowledged")
        
    now = datetime.now(timezone.utc)
    await db["alerts"].update_one(
        {"alert_id": alert_id},
        {"$set": {"status": "ACKNOWLEDGED", "updated_at": now}}
    )
    return {"msg": "Alert acknowledged"}

class ResolveAlertRequest(BaseModel):
    resolution_reason: str
    resolution_note: Optional[str] = None

@router.patch("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str, 
    request: ResolveAlertRequest, 
    current_user: TokenData = Depends(get_current_user)
):
    db = get_db()
    alert = await db["alerts"].find_one({"alert_id": alert_id})
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
        
    if alert["status"] == "RESOLVED":
        raise HTTPException(status_code=400, detail="Alert is already resolved")
        
    now = datetime.now(timezone.utc)
    await db["alerts"].update_one(
        {"alert_id": alert_id},
        {"$set": {
            "status": "RESOLVED", 
            "updated_at": now,
            "resolved_at": now,
            "resolved_by": current_user.username,
            "resolution_reason": request.resolution_reason,
            "resolution_note": request.resolution_note
        }}
    )
    return {"msg": "Alert resolved"}
