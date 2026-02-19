from pydantic import BaseModel, Field, validator
from typing import Optional

class MFAVerifyRequest(BaseModel):
    """Schema for MFA verification request."""
    code: str = Field(..., min_length=6, max_length=6, description="The 6-digit MFA code")

    @validator('code')
    def validate_code_format(cls, v):
        if not v.isdigit():
            raise ValueError("MFA code must be numeric")
        if len(v) != 6:
            raise ValueError("MFA code must be exactly 6 digits")
        return v

class MFASetupResponse(BaseModel):
    """Response model for MFA setup."""
    secret: str
    provisioning_uri: str
    qr_code: str
    recovery_codes: list[str]

class MFARecoveryRequest(BaseModel):
    """Schema for MFA recovery code verification."""
    recovery_code: str = Field(..., min_length=8, max_length=10, description="A recovery code for MFA")

class MFADisableRequest(BaseModel):
    """Schema for disabling MFA."""
    password: str = Field(..., description="User's password for verification")

class MFAResponse(BaseModel):
    """Generic MFA response model."""
    success: bool
    message: str
    data: Optional[dict] = None
