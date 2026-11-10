from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User
from ..portfolio.service import audit
from ..security.auth import create_token, current_user, hash_password, login_limiter, validate_password_strength, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=1, max_length=256)


@router.post("/register", dependencies=[Depends(login_limiter)])
def register(c: Credentials, db: Session = Depends(get_db)):
    # Single-user personal platform: registration closes after the first account unless enabled.
    n = db.scalar(select(func.count()).select_from(User))
    if n and not get_settings().allow_registration:
        raise HTTPException(403, "registration disabled")
    if db.scalar(select(User).where(User.username == c.username)):
        raise HTTPException(409, "username taken")
    validate_password_strength(c.password)
    u = User(username=c.username, password_hash=hash_password(c.password))
    db.add(u)
    db.flush()
    audit(db, "register", "user", u.id, user_id=u.id)
    db.commit()
    return {"access_token": create_token(u), "token_type": "bearer", "username": u.username}


@router.post("/login", dependencies=[Depends(login_limiter)])
def login(c: Credentials, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == c.username))
    if not u or not verify_password(c.password, u.password_hash):
        raise HTTPException(401, "invalid credentials")
    return {"access_token": create_token(u), "token_type": "bearer", "username": u.username}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username}
