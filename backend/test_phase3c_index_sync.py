import sys
import uuid
import asyncio
import certifi
import warnings
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timezone

warnings.filterwarnings("ignore", category=DeprecationWarning)

sys.path.append(".")
from app.db.mongodb import db, init_indexes, validate_test_db_name, safe_drop_test_database
from app.core.config import settings

TEST_DB_NAME = validate_test_db_name("smart_inventory_test_phase3c")
settings.MONGODB_DB_NAME = TEST_DB_NAME


async def run_phase3c_index_sync_tests():
    print(f"Connecting to isolated test database: {TEST_DB_NAME}...")
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    database = db.client.get_database(TEST_DB_NAME)

    # Clean slate on test db
    await safe_drop_test_database(db.client, TEST_DB_NAME)

    try:
        # -------------------------------------------------------------
        # Test 1: init_indexes creates unique_active_alert_per_type
        # -------------------------------------------------------------
        print("Running init_indexes()...")
        await init_indexes()

        cursor = await database["alerts"].list_indexes()
        indexes = await cursor.to_list(length=50)
        target_idx = next((i for i in indexes if i.get("name") == "unique_active_alert_per_type"), None)

        assert target_idx is not None, "unique_active_alert_per_type index not found after init_indexes()"
        assert target_idx.get("name") == "unique_active_alert_per_type", "Index name mismatch"
        assert list(target_idx.get("key").items()) == [("alert_type", 1)], f"Index key mismatch: {target_idx.get('key')}"
        assert target_idx.get("unique") is True, "Index unique flag is not True"
        assert target_idx.get("partialFilterExpression") == {"status": {"$in": ["OPEN", "ACKNOWLEDGED"]}}, (
            f"Index partialFilterExpression mismatch: {target_idx.get('partialFilterExpression')}"
        )
        print("PASS: Test 1 - unique_active_alert_per_type verified (name, key, unique, partialFilterExpression)")

        # -------------------------------------------------------------
        # Test 2: Idempotency - repeated init_indexes execution is safe
        # -------------------------------------------------------------
        print("Running init_indexes() second time to test idempotency...")
        await init_indexes()

        cursor_after = await database["alerts"].list_indexes()
        indexes_after_repeat = await cursor_after.to_list(length=50)
        matching_indexes = [i for i in indexes_after_repeat if i.get("name") == "unique_active_alert_per_type"]
        assert len(matching_indexes) == 1, f"Expected exactly 1 index instance, found {len(matching_indexes)}"
        assert len(indexes_after_repeat) == len(indexes), "Index count changed on repeated init_indexes()"
        print("PASS: Test 2 - Repeated init_indexes() execution is completely idempotent and safe")

        # -------------------------------------------------------------
        # Test 3: Partial unique constraint enforcement on active alerts
        # -------------------------------------------------------------
        now = datetime.now(timezone.utc)
        doc_open = {
            "alert_id": str(uuid.uuid4()),
            "alert_type": "QR_EXCEPTION_SPIKE",
            "status": "OPEN",
            "exception_count": 5,
            "created_at": now
        }
        await database["alerts"].insert_one(doc_open)

        doc_ack = {
            "alert_id": str(uuid.uuid4()),
            "alert_type": "QR_EXCEPTION_SPIKE",
            "status": "ACKNOWLEDGED",
            "exception_count": 6,
            "created_at": now
        }
        collision_detected = False
        try:
            await database["alerts"].insert_one(doc_ack)
        except DuplicateKeyError:
            collision_detected = True

        assert collision_detected, "Expected DuplicateKeyError on competing active alert insert, but insert succeeded!"
        print("PASS: Test 3 - Duplicate active alert correctly blocked by MongoDB partial unique constraint")

        # -------------------------------------------------------------
        # Test 4: Resolved alerts are not blocked by the partial filter
        # -------------------------------------------------------------
        doc_resolved_1 = {
            "alert_id": str(uuid.uuid4()),
            "alert_type": "QR_EXCEPTION_SPIKE",
            "status": "RESOLVED",
            "exception_count": 5,
            "created_at": now
        }
        doc_resolved_2 = {
            "alert_id": str(uuid.uuid4()),
            "alert_type": "QR_EXCEPTION_SPIKE",
            "status": "RESOLVED",
            "exception_count": 7,
            "created_at": now
        }
        await database["alerts"].insert_one(doc_resolved_1)
        await database["alerts"].insert_one(doc_resolved_2)
        print("PASS: Test 4 - Multiple RESOLVED alerts successfully allowed by partial filter")

    finally:
        await safe_drop_test_database(db.client, TEST_DB_NAME)
        print(f"Isolated test database {TEST_DB_NAME} dropped cleanly.")


if __name__ == "__main__":
    asyncio.run(run_phase3c_index_sync_tests())
    print("\nALL PHASE 3C INDEX SYNCHRONIZATION TESTS PASSED SUCCESSFULLY!")
