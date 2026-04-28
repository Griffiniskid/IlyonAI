from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.core.security import create_token, decode_token, hash_password, verify_password, verify_metamask, verify_phantom
from app.schemas.auth import RegisterRequest, LoginRequest, MetaMaskAuthRequest, PhantomAuthRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        user_id = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_optional_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Optional[User]:
    if not token:
        return None
    try:
        user_id = decode_token(token)
        return db.query(User).filter(User.id == user_id).first()
    except Exception:
        return None


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    token = create_token(user.id)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/metamask", response_model=TokenResponse)
def metamask_auth(body: MetaMaskAuthRequest, db: Session = Depends(get_db)):
    if not verify_metamask(body.address, body.message, body.signature):
        raise HTTPException(status_code=400, detail="Invalid MetaMask signature")
    user = db.query(User).filter(User.wallet_address == body.address.lower()).first()
    if not user:
        display = body.display_name or f"{body.address[:6]}...{body.address[-4:]}"
        user = User(wallet_address=body.address.lower(), display_name=display)
        db.add(user)
        db.commit()
        db.refresh(user)
    token = create_token(user.id)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/phantom", response_model=TokenResponse)
def phantom_auth(body: PhantomAuthRequest, db: Session = Depends(get_db)):
    if not verify_phantom(body.public_key, body.message, body.signature):
        raise HTTPException(status_code=400, detail="Invalid Phantom signature")

    wallet_key = body.public_key.strip()
    user = db.query(User).filter(User.wallet_address == wallet_key).first()
    if not user:
        display = body.display_name or f"{wallet_key[:6]}...{wallet_key[-4:]}"
        user = User(wallet_address=wallet_key, display_name=display)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_token(user.id)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
