from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from app.models.user import Token
from app.core.security import verify_password, create_access_token
from app.db.mongodb import get_db
from datetime import timedelta

router = APIRouter()

@router.post("/login", response_model=Token)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    db = get_db()
    user = await db["users"].find_one({"username": form_data.username})
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
        
    if not user.get("is_active", True):
        raise HTTPException(status_code=400, detail="Inactive user")
    
    try:
        is_valid = verify_password(form_data.password, user["hashed_password"])
    except Exception:
        is_valid = False
        
    if not is_valid:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
        
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user.get("role", "ADMIN")},
        expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")
