from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    display_name: str = Field(..., min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MetaMaskAuthRequest(BaseModel):
    address: str = Field(..., description="Ethereum wallet address (0x...)")
    message: str = Field(..., description="Signed message containing timestamp")
    signature: str = Field(..., description="Hex signature from personal_sign")
    display_name: Optional[str] = Field(None, max_length=100)


class PhantomAuthRequest(BaseModel):
    public_key: str = Field(..., description="Solana wallet public key (base58)")
    message: str = Field(..., description="Signed message containing timestamp")
    signature: str = Field(..., description="Signature from Phantom signMessage (base64/base58/hex)")
    display_name: Optional[str] = Field(None, max_length=100)


class TokenResponse(BaseModel):
    token: str
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    email: Optional[str] = None
    wallet_address: Optional[str] = None
    display_name: str

    model_config = {"from_attributes": True}


TokenResponse.model_rebuild()
