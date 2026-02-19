from typing import List, Optional
from pydantic import BaseModel

class Token(BaseModel):
    """Schema for access token response."""
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str


class TokenData(BaseModel):
    """Schema for token data."""
    username: Optional[str] = None
    scopes: List[str] = []


class TokenPayload(BaseModel):
    """Schema for token payload."""
    sub: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None
    jti: Optional[str] = None
