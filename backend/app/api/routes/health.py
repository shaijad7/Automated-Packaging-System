import asyncio
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.db.mongodb import get_db

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Public health check endpoint.
    Verifies backend responsiveness and MongoDB connectivity with safe timeouts.
    Never exposes raw exceptions, credentials, or internal topology.
    """
    try:
        db = get_db()
        await asyncio.wait_for(db.command("ping"), timeout=3.0)
        return {"status": "healthy", "database": "connected"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "detail": "Database connection failed"
            }
        )
