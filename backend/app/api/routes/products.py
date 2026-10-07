from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import io
import qrcode
from PIL import Image, ImageDraw, ImageFont

from app.models.product import ProductCreate, ProductInDB
from app.models.user import TokenData
from app.api.deps import get_current_user, get_current_active_admin
from app.db.mongodb import get_db

router = APIRouter()

@router.get("/", response_model=list[ProductInDB])
async def list_products(current_user: TokenData = Depends(get_current_user)):
    db = get_db()
    products = await db["products"].find().to_list(1000)
    return [ProductInDB(**p) for p in products]

@router.post("/", response_model=ProductInDB)
async def create_product(
    product: ProductCreate, 
    current_user: TokenData = Depends(get_current_active_admin)
):
    db = get_db()
    
    # Enforce strictly generated QR code format
    qr_code = f"INV|{product.sku}"
    
    existing = await db["products"].find_one({"$or": [{"sku": product.sku}, {"qr_code": qr_code}]})
    if existing:
        raise HTTPException(status_code=400, detail="Product with this SKU already exists")
    
    product_in_db = ProductInDB(**product.model_dump(), qr_code=qr_code)
    product_dict = product_in_db.model_dump()
    await db["products"].insert_one(product_dict)
    
    # Initialize inventory to 0
    await db["inventory"].insert_one({"sku": product.sku, "quantity": 0})
    
    return product_in_db

@router.delete("/{sku}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(sku: str, current_user: TokenData = Depends(get_current_active_admin)):
    db = get_db()
    result = await db["products"].delete_one({"sku": sku})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Optionally delete inventory too
    await db["inventory"].delete_one({"sku": sku})
    return None

@router.get("/{sku}/label")
async def generate_label(sku: str, current_user: TokenData = Depends(get_current_user)):
    db = get_db()
    product = await db["products"].find_one({"sku": sku})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Generate Standard Geometric QR Code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(product["qr_code"])
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Create Label Canvas
    width, qr_height = qr_img.size
    padding = 20
    text_area_height = 60
    height = qr_height + text_area_height + padding * 2
    
    label_img = Image.new("RGB", (width + padding * 2, height), "white")
    draw = ImageDraw.Draw(label_img)
    
    # Draw Product Name Text
    font = ImageFont.load_default()
    text = product["name"]
    
    # Bounding box for text centering (fallback for older Pillow versions)
    try:
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
    except AttributeError:
        # Fallback if textbbox is missing in some environments
        text_width = font.getlength(text) if hasattr(font, 'getlength') else len(text) * 6
        
    text_x = (label_img.width - text_width) // 2
    draw.text((text_x, padding), text, font=font, fill="black")
    
    # Paste QR Code
    label_img.paste(qr_img, (padding, padding + text_area_height))
    
    # Return as StreamingResponse
    img_byte_arr = io.BytesIO()
    label_img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return StreamingResponse(img_byte_arr, media_type="image/png")
