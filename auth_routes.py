from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, require_admin, verify_password
from db import get_db
from models import User
from schemas import (
    AdminUserUpdate,
    LoginRequest,
    ProfileUpdate,
    PublicProfile,
    SignupRequest,
    Token,
    UserOut,
)

router = APIRouter()


@router.post("/auth/signup", response_model=Token)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(name=req.name, email=req.email, password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=create_access_token(user.id, user.role))


@router.post("/auth/login", response_model=Token)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="Account is banned")
    return Token(access_token=create_access_token(user.id, user.role))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/users/me", response_model=UserOut)
def update_profile(
    req: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if req.name is not None:
        user.name = req.name
    if req.github_url is not None:
        user.github_url = req.github_url or None
    if req.linkedin_url is not None:
        user.linkedin_url = req.linkedin_url or None
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=PublicProfile)
def get_public_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/admin/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.created_at).all()


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    req: AdminUserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and (req.role == "user" or req.is_banned):
        raise HTTPException(status_code=400, detail="Admins can't demote or ban themselves")

    if req.role is not None:
        if req.role not in ("user", "admin"):
            raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")
        user.role = req.role
    if req.is_banned is not None:
        user.is_banned = req.is_banned

    db.commit()
    db.refresh(user)
    return user


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Admins can't delete themselves")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
