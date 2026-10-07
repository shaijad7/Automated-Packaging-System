from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt.exceptions import InvalidTokenError
from app.core.config import settings
from app.models.user import TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> TokenData:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        role: str | None = payload.get("role")
        if username is None or role is None or role != "ADMIN":
            raise credentials_exception
        token_data = TokenData(username=username, role=role)
    except InvalidTokenError:
        raise credentials_exception
    return token_data

def get_current_active_admin(current_user: Annotated[TokenData, Depends(get_current_user)]) -> TokenData:
    return current_user

from fastapi.security import APIKeyHeader
import hmac

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: Annotated[str | None, Depends(api_key_header)]) -> str:
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
        )
    if not hmac.compare_digest(api_key.encode("utf-8"), settings.EDGE_NODE_API_KEY.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )
    return "edge_node"
