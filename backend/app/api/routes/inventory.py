from fastapi import APIRouter, Depends
from app.models.inventory import InventoryItem
from app.models.user import TokenData
from app.api.deps import get_current_user
from app.db.mongodb import get_db

router = APIRouter()

@router.get("/", response_model=list[InventoryItem])
async def get_inventory(current_user: TokenData = Depends(get_current_user)):
    db = get_db()
    inventory = await db["inventory"].find().to_list(1000)
    return [InventoryItem(**i) for i in inventory]
