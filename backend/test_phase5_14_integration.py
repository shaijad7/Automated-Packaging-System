import sys
import os
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import certifi
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Ensure backend and cv_pipeline are on sys.path
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("cv_pipeline"))

from app.main import app
from app.db.mongodb import db, init_indexes, validate_test_db_name, safe_drop_test_database
from app.core.config import settings
from app.core.security import get_password_hash, create_access_token

# Real CV pipeline modules
from spool import EventSpool
from qr.payload_validator import validate_qr_payload

TEST_DB_NAME = validate_test_db_name("smart_inventory_test_p5_14")
settings.MONGODB_DB_NAME = TEST_DB_NAME

client = TestClient(app)
edge_headers = {"X-API-Key": settings.EDGE_NODE_API_KEY}


def validate_acknowledgement_helper(response):
    """
    Exact implementation of validate_acknowledgement from cv_pipeline/run_pipeline.py.
    Validates backend HTTP response status and JSON acknowledgement body.
    Requires successful HTTP status and JSON object with 'msg' in ('Event recorded', 'Event already processed').
    """
    if response.status_code >= 400:
        raise ValueError(f"HTTP Error {response.status_code}: {response.text}")
    try:
        resp_json = response.json()
    except Exception as json_err:
        raise ValueError(f"Invalid JSON in backend response: {json_err}") from json_err

    if not isinstance(resp_json, dict) or resp_json.get("msg") not in (
        "Event recorded",
        "Event already processed",
    ):
        msg_preview = str(resp_json)[:100] if isinstance(resp_json, dict) else type(resp_json).__name__
        raise ValueError(f"Unexpected acknowledgement body from backend: {msg_preview}")
    return resp_json


async def run_integration_audit():
    print(f"Connecting to isolated test database: {TEST_DB_NAME}...")
    db.client = AsyncMongoClient(settings.MONGODB_URI, tlsCAFile=certifi.where())
    database = db.client.get_database(TEST_DB_NAME)

    await safe_drop_test_database(db.client, TEST_DB_NAME)
    await init_indexes()

    # Create temporary isolated SQLite spool
    test_spool_dir = Path("backend/test_spool_5_14")
    test_spool_dir.mkdir(parents=True, exist_ok=True)
    test_spool_path = test_spool_dir / "spool_audit.db"
    if test_spool_path.exists():
        test_spool_path.unlink()

    spool = EventSpool(test_spool_path)

    try:
        # Seed Admin user for product and inventory queries
        admin_hash = get_password_hash("AdminPass123!")
        await database["users"].insert_one({
            "username": "audit_admin",
            "hashed_password": admin_hash,
            "role": "ADMIN",
            "is_active": True
        })
        admin_token = create_access_token(data={"sub": "audit_admin", "role": "ADMIN"})
        admin_auth = {"Authorization": f"Bearer {admin_token}"}

        # Seed Active Product
        active_prod = {
            "name": "Heavy Duty Caster",
            "sku": "CST-001",
            "description": "Industrial polyurethane wheel caster",
            "is_active": True
        }
        client.post("/api/products/", json=active_prod, headers=admin_auth)

        # Seed Inactive Product
        inactive_prod = {
            "name": "Deprecated Bearing",
            "sku": "BRG-OLD",
            "description": "Legacy roller bearing",
            "is_active": False
        }
        client.post("/api/products/", json=inactive_prod, headers=admin_auth)

        # ---------------------------------------------------------------------
        # Step 2.1: Valid INV|SKU QR for active product -> correct event, increments stock once
        # ---------------------------------------------------------------------
        raw_qr_input = "  INV|CST-001  "
        is_valid, norm_payload, extracted_sku = validate_qr_payload(raw_qr_input)
        assert is_valid is True
        assert norm_payload == "INV|CST-001"
        assert extracted_sku == "CST-001"

        event_1_id = f"evt-e2e-{uuid.uuid4()}"
        event_1 = {
            "event_id": event_1_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "track_id": 1,
            "qr_status": "VALID_QR",
            "qr_payload": norm_payload,
            "count_direction": "A_TO_B"
        }
        spool.enqueue(event_1)
        assert spool.get_pending_count() == 1

        # Transmit via edge endpoint
        resp1 = client.post("/api/events/", json=event_1, headers=edge_headers)
        ack1 = validate_acknowledgement_helper(resp1)
        assert ack1 == {"msg": "Event recorded"}
        spool.mark_delivered(event_1_id)

        assert spool.get_pending_count() == 0
        inv_cst = await database["inventory"].find_one({"sku": "CST-001"})
        assert inv_cst["quantity"] == 1
        print("PASS (Check 1): Valid INV|SKU event enqueued, delivered, acknowledged, and stock incremented from 0 to 1.")

        # ---------------------------------------------------------------------
        # Step 2.2: Invalid, unreadable, missing, ambiguous, and unknown-product QR results
        # ---------------------------------------------------------------------
        raw_invalid_inputs = [
            ("INVALID_QR", "CORRUPT_PAYLOAD", 2),
            ("NO_QR", None, 3),
            ("UNREADABLE_QR", None, 4),
            ("AMBIGUOUS", None, 5),
            ("VALID_QR", "INV|UNKNOWN-SKU-999", 6),  # Valid format, but unknown SKU
        ]

        for qr_status, qr_payload, track_id in raw_invalid_inputs:
            evt_id = f"evt-invalid-{uuid.uuid4()}"
            evt = {
                "event_id": evt_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "track_id": track_id,
                "qr_status": qr_status,
                "qr_payload": qr_payload,
                "count_direction": "A_TO_B"
            }
            spool.enqueue(evt)
            resp = client.post("/api/events/", json=evt, headers=edge_headers)
            ack = validate_acknowledgement_helper(resp)
            assert ack == {"msg": "Event recorded"}
            spool.mark_delivered(evt_id)

            saved_evt = await database["events"].find_one({"event_id": evt_id})
            assert saved_evt["status"] == "RECORDED"
            assert saved_evt["sku"] is None

        # Verify stock did not increment
        inv_check = await database["inventory"].find_one({"sku": "CST-001"})
        assert inv_check["quantity"] == 1
        assert await database["inventory"].find_one({"sku": "UNKNOWN-SKU-999"}) is None
        print("PASS (Check 2): Invalid, unreadable, missing, ambiguous, and unknown-SKU events recorded as RECORDED without incrementing stock.")

        # ---------------------------------------------------------------------
        # Step 2.3: Inactive products do not increment stock
        # ---------------------------------------------------------------------
        evt_inact_id = f"evt-inact-{uuid.uuid4()}"
        evt_inact = {
            "event_id": evt_inact_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "track_id": 7,
            "qr_status": "VALID_QR",
            "qr_payload": "INV|BRG-OLD",
            "count_direction": "A_TO_B"
        }
        spool.enqueue(evt_inact)
        resp_inact = client.post("/api/events/", json=evt_inact, headers=edge_headers)
        ack_inact = validate_acknowledgement_helper(resp_inact)
        assert ack_inact == {"msg": "Event recorded"}
        spool.mark_delivered(evt_inact_id)

        saved_inact = await database["events"].find_one({"event_id": evt_inact_id})
        assert saved_inact["status"] == "RECORDED"
        assert saved_inact["sku"] is None
        inv_brg = await database["inventory"].find_one({"sku": "BRG-OLD"})
        assert inv_brg["quantity"] == 0
        print("PASS (Check 3): Inactive product QR scan recorded as RECORDED with stock unchanged at 0.")

        # ---------------------------------------------------------------------
        # Step 2.4: Retrying identical event_id does not increment stock twice (Idempotency)
        # ---------------------------------------------------------------------
        # Re-post event_1 (already delivered earlier)
        resp_retry = client.post("/api/events/", json=event_1, headers=edge_headers)
        ack_retry = validate_acknowledgement_helper(resp_retry)
        assert ack_retry == {"msg": "Event already processed"}

        inv_after_retry = await database["inventory"].find_one({"sku": "CST-001"})
        assert inv_after_retry["quantity"] == 1
        print("PASS (Check 4): Re-sending same event_id acknowledged as 'Event already processed' with zero stock change.")

        # ---------------------------------------------------------------------
        # Step 2.5: Distinct valid event is processed according to business rules
        # ---------------------------------------------------------------------
        event_2_id = f"evt-e2e-{uuid.uuid4()}"
        event_2 = {
            "event_id": event_2_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "track_id": 8,
            "qr_status": "VALID_QR",
            "qr_payload": "INV|CST-001",
            "count_direction": "A_TO_B"
        }
        spool.enqueue(event_2)
        resp2 = client.post("/api/events/", json=event_2, headers=edge_headers)
        ack2 = validate_acknowledgement_helper(resp2)
        assert ack2 == {"msg": "Event recorded"}
        spool.mark_delivered(event_2_id)

        inv_cst2 = await database["inventory"].find_one({"sku": "CST-001"})
        assert inv_cst2["quantity"] == 2
        print("PASS (Check 5): Distinct valid event increments inventory to 2.")

        # ---------------------------------------------------------------------
        # Step 2.6: Backend responses match CV client's strict acknowledgement contract
        # ---------------------------------------------------------------------
        assert ack1["msg"] in ("Event recorded", "Event already processed")
        assert ack_retry["msg"] in ("Event recorded", "Event already processed")

        # Simulate unexpected responses and verify validate_acknowledgement catches them
        class MockResp:
            def __init__(self, status_code, json_data):
                self.status_code = status_code
                self._json = json_data
                self.text = str(json_data)
            def json(self):
                return self._json

        try:
            validate_acknowledgement_helper(MockResp(200, {"status": "ok"}))
            assert False, "Should have rejected unexpected JSON body"
        except ValueError as e:
            assert "Unexpected acknowledgement body" in str(e)

        try:
            validate_acknowledgement_helper(MockResp(500, {"detail": "Internal error"}))
            assert False, "Should have rejected HTTP 500"
        except ValueError as e:
            assert "HTTP Error 500" in str(e)

        print("PASS (Check 6): Strict acknowledgement contract validation verifies exact msg values and catches unexpected payloads.")

        # ---------------------------------------------------------------------
        # Step 2.7: Invalid API keys are rejected
        # ---------------------------------------------------------------------
        resp_no_key = client.post("/api/events/", json=event_2)
        assert resp_no_key.status_code == 401
        assert "Missing API Key" in resp_no_key.json()["detail"]

        resp_bad_key = client.post("/api/events/", json=event_2, headers={"X-API-Key": "wrong_secret"})
        assert resp_bad_key.status_code == 401
        assert "Invalid API Key" in resp_bad_key.json()["detail"]
        print("PASS (Check 7): Missing and invalid X-API-Key rejected with HTTP 401.")

        # ---------------------------------------------------------------------
        # Step 2.8: Network errors and HTTP failures preserve pending events in SQLite spool
        # ---------------------------------------------------------------------
        event_fail_id = f"evt-fail-{uuid.uuid4()}"
        event_fail = {
            "event_id": event_fail_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "track_id": 9,
            "qr_status": "VALID_QR",
            "qr_payload": "INV|CST-001",
            "count_direction": "A_TO_B"
        }
        spool.enqueue(event_fail)
        assert spool.get_pending_count() == 1

        # Simulate transmission failure
        spool.record_attempt(event_fail_id, status="PENDING", error="Simulated Network Timeout")
        spool_rec = spool.get_event(event_fail_id)
        assert spool_rec is not None
        assert spool_rec["status"] == "PENDING"
        assert spool_rec["attempts"] == 1
        assert "Simulated Network Timeout" in spool_rec["last_error"]
        assert spool.get_pending_count() == 1
        print("PASS (Check 8): Failed transmission preserves pending event in durable SQLite spool with attempt metadata.")

        # ---------------------------------------------------------------------
        # Step 2.9: Restart recovery without double-counting
        # ---------------------------------------------------------------------
        spool.close()

        # Re-initialize spool on the same SQLite file (simulating pipeline reboot)
        restarted_spool = EventSpool(test_spool_path)
        pending = restarted_spool.get_pending_events()
        assert len(pending) == 1
        assert pending[0]["event_id"] == event_fail_id

        # Deliver the recovered event
        resp_recov = client.post("/api/events/", json=pending[0], headers=edge_headers)
        ack_recov = validate_acknowledgement_helper(resp_recov)
        assert ack_recov == {"msg": "Event recorded"}
        restarted_spool.mark_delivered(event_fail_id)

        assert restarted_spool.get_pending_count() == 0
        inv_after_recov = await database["inventory"].find_one({"sku": "CST-001"})
        assert inv_after_recov["quantity"] == 3
        restarted_spool.close()
        print("PASS (Check 9): Pipeline restart cleanly recovers pending spool events, delivering without double-counting.")

        # ---------------------------------------------------------------------
        # Step 2.10 & 2.11: Heartbeat telemetry separation and zero inventory mutation
        # ---------------------------------------------------------------------
        events_count_before = await database["events"].count_documents({})
        inv_before = await database["inventory"].find().to_list(100)

        heartbeat_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "camera": "UP",
            "camera_details": "Camera stream active (1280x720 @ 30fps)",
            "model": "UP",
            "model_details": "YOLOv8 custom box model active (10.5ms)",
            "fps": 30.0,
            "last_frame_timestamp": datetime.now(timezone.utc).isoformat(),
            "last_inference_timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Send edge telemetry
        hb_resp = client.post("/api/edge/heartbeat", json=heartbeat_payload, headers=edge_headers)
        assert hb_resp.status_code == 200
        assert hb_resp.json()["status"] == "recorded"

        # Verify telemetry exposed via system-health
        health_resp = client.get("/api/dashboard/system-health", headers=admin_auth)
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["camera_status"] == "UP"
        assert health_data["model_status"] == "UP"
        assert health_data["fps"] == 30.0

        # Verify zero mutation in database events and inventory
        events_count_after = await database["events"].count_documents({})
        assert events_count_after == events_count_before

        inv_after = await database["inventory"].find().to_list(100)
        assert len(inv_before) == len(inv_after)
        for b_item, a_item in zip(inv_before, inv_after):
            assert b_item["sku"] == a_item["sku"]
            assert b_item["quantity"] == a_item["quantity"]

        print("PASS (Check 10 & 11): Heartbeat telemetry is strictly isolated from events and inventory; zero inventory mutations occur during health reporting.")

    finally:
        # Clean up isolated test database
        await safe_drop_test_database(db.client, TEST_DB_NAME)
        await db.client.close()

        # Clean up temporary SQLite spool
        if test_spool_path.exists():
            try:
                test_spool_path.unlink()
            except Exception:
                pass
        for f in test_spool_dir.glob("spool_audit.db*"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            test_spool_dir.rmdir()
        except Exception:
            pass

    print("\nALL 11 PHASE 5.14 CV PIPELINE TO INVENTORY INTEGRATION CHECKS PASSED EMPIRICALLY!")


if __name__ == "__main__":
    asyncio.run(run_integration_audit())
