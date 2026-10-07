from fastapi import APIRouter, Depends
from app.models.event import EventCreate, EventInDB
from app.models.user import TokenData
from app.api.deps import get_current_user, verify_api_key
from app.db.mongodb import get_db
from pymongo.errors import DuplicateKeyError
import pymongo
from fastapi import BackgroundTasks
from app.services.alerts import evaluate_qr_exception_alert

router = APIRouter()

@router.get("/", response_model=list[EventInDB])
async def list_events(limit: int = 50, current_user: TokenData = Depends(get_current_user)):
    db = get_db()
    events = await db["events"].find().sort("timestamp", pymongo.DESCENDING).limit(limit).to_list(limit)
    return [EventInDB(**e) for e in events]

@router.post("/")
async def create_event(event: EventCreate, background_tasks: BackgroundTasks, edge_node: str = Depends(verify_api_key)):
    from app.db.mongodb import db as db_manager
    db = get_db()
    client = db_manager.client
    
    # 1. Product Lookup
    product = None
    sku = None
    if event.qr_payload:
        product = await db["products"].find_one({"qr_code": event.qr_payload})
        if product and product.get("is_active", True) is True:
            sku = product["sku"]
    
    # 2. Event Document prep
    event_doc = event.model_dump()
    event_doc["sku"] = sku
    
    status = "SUCCESS" if event.qr_status == "VALID_QR" and sku else "RECORDED"
    event_doc["status"] = status
    
    # 3. Duplicate Protection (Idempotency) & Atomicity
    try:
        async with client.start_session() as session:
            await session.start_transaction()
            try:
                await db["events"].insert_one(event_doc, session=session)
                
                # 4. Process Valid Scan (Inventory update)
                if status == "SUCCESS":
                    await db["inventory"].update_one(
                        {"sku": sku},
                        {"$inc": {"quantity": 1}},
                        upsert=True,
                        session=session
                    )
                await session.commit_transaction()
            except Exception as e:
                await session.abort_transaction()
                raise e
    except DuplicateKeyError:
        # Event already processed, safely ignore and return OK
        return {"msg": "Event already processed"}
    
    background_tasks.add_task(evaluate_qr_exception_alert, db)
    
    return {"msg": "Event recorded"}

