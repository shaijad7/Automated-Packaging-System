from pymongo import AsyncMongoClient
import certifi
from app.core.config import settings

class Database:
    client: AsyncMongoClient | None = None

db = Database()

def get_db():
    if db.client is None:
        raise Exception("Database not initialized")
    return db.client.get_database("smart_inventory")

async def init_indexes():
    db = get_db()
    # Products indexes
    await db["products"].create_index("sku", unique=True)
    await db["products"].create_index("qr_code", unique=True)
    
    # Inventory indexes
    await db["inventory"].create_index("sku", unique=True)
    
    # Events indexes
    await db["events"].create_index("event_id", unique=True)
    await db["events"].create_index([("timestamp", -1)])
    
    # Users indexes
    await db["users"].create_index("username", unique=True)
    
    # Alerts indexes
    await db["alerts"].create_index("alert_id", unique=True)
    await db["alerts"].create_index("status")
    await db["alerts"].create_index("alert_type")
    await db["alerts"].create_index([("created_at", -1)])
    await db["alerts"].create_index([("window_start", -1)])
