from pydantic import BaseModel, Field

class ProductBase(BaseModel):
    sku: str
    name: str
    description: str | None = None
    is_active: bool = True

class ProductCreate(ProductBase):
    pass

class ProductInDB(ProductBase):
    qr_code: str
