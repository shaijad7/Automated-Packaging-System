from fastapi import APIRouter, HTTPException
from app.db.mongodb import get_db

router = APIRouter()

@router.get("/health")
async def health_check():
    try:
        db = get_db()
        await db.command('ping')
        db_status = "connected"
    except Exception as e:
        db_status = "disconnected"
        raise HTTPException(status_code=503, detail="Database connection failed")
        
    return {"status": "healthy", "database": db_status}
