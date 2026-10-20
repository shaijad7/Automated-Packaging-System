from pymongo import AsyncMongoClient
import certifi
from app.core.config import settings

class Database:
    client: AsyncMongoClient | None = None

db = Database()

UNSAFE_TEST_DB_NAMES = frozenset({"smart_inventory", "production", "prod", "main", "default", "admin"})

def validate_test_db_name(db_name: str) -> str:
    """
    Validates that a database name is explicitly designated for testing.
    Rejects production, default, or un-isolated database targets.
    """
    if not db_name or not isinstance(db_name, str):
        raise ValueError(f"Invalid database name: {db_name}")

    normalized = db_name.strip().lower()
    if normalized in UNSAFE_TEST_DB_NAMES or "test" not in normalized:
        raise ValueError(
            f"Unsafe database target rejected for testing: '{db_name}'. "
            f"Test operations require an explicit test database name containing 'test' (e.g. 'smart_inventory_test_*')."
        )
    return db_name

async def safe_drop_test_database(client: AsyncMongoClient, db_name: str) -> None:
    """
    Safely drops a database only after verifying it is an isolated test database.
    Prevents accidental dropping of production or staging databases.
    """
    validate_test_db_name(db_name)
    await client.drop_database(db_name)

def get_db():
    if db.client is None:
        raise Exception("Database not initialized")
    return db.client.get_database(getattr(settings, "MONGODB_DB_NAME", "smart_inventory"))

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
    await db["alerts"].create_index(
        [("alert_type", 1)],
        unique=True,
        partialFilterExpression={
            "status": {"$in": ["OPEN", "ACKNOWLEDGED"]}
        },
        name="unique_active_alert_per_type"
    )
