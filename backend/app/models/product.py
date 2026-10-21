from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional

class ProductBase(BaseModel):
    sku: str
    name: str
    description: str | None = None
    is_active: bool = True

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            raise ValueError("Product name cannot be null when supplied")
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Product name cannot be empty or whitespace only")
        return trimmed

    @field_validator("is_active")
    @classmethod
    def validate_active_not_null(cls, v: Optional[bool]) -> Optional[bool]:
        if v is None:
            raise ValueError("is_active cannot be null when supplied")
        return v

class ProductInDB(ProductBase):
    qr_code: str
