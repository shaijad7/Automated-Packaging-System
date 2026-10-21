from fastapi import APIRouter, Depends
from app.api.deps import verify_api_key
from app.models.health import EdgeHeartbeatPayload
from app.services.system_health import record_edge_heartbeat

router = APIRouter()

@router.post("/heartbeat")
async def receive_heartbeat(
    payload: EdgeHeartbeatPayload,
    _edge_node: str = Depends(verify_api_key),
):
    """
    Authenticated ingestion endpoint for CV edge telemetry heartbeats.
    Protected strictly by X-API-Key (EDGE_NODE_API_KEY).
    Records runtime camera and model health without mutating database or inventory.
    """
    result = record_edge_heartbeat(payload)
    return result
