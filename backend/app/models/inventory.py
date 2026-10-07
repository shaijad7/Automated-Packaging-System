from pydantic import BaseModel

class InventoryItem(BaseModel):
    sku: str
    quantity: int
