from fastapi import APIRouter, Depends, HTTPException, status

import models
from auth import create_access_token, get_current_user, hash_password, require_admin, verify_password
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
def signup(req: SignupRequest):
    if models.get_user_by_email(req.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.create_user(name=req.name, email=req.email, password_hash=hash_password(req.password))
    return Token(access_token=create_access_token(user["id"], user["role"]))


@router.post("/auth/login", response_model=Token)
def login(req: LoginRequest):
    user = models.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if user["is_banned"]:
        raise HTTPException(status_code=403, detail="Account is banned")
    return Token(access_token=create_access_token(user["id"], user["role"]))


@router.get("/auth/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return user


@router.patch("/users/me", response_model=UserOut)
def update_profile(req: ProfileUpdate, user: dict = Depends(get_current_user)):
    fields = {}
    if req.name is not None:
        fields["name"] = req.name
    if req.github_url is not None:
        fields["github_url"] = req.github_url or None
    if req.linkedin_url is not None:
        fields["linkedin_url"] = req.linkedin_url or None
    return models.update_user(user, **fields)


@router.get("/users/{user_id}", response_model=PublicProfile)
def get_public_profile(user_id: str):
    user = models.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/admin/users", response_model=list[UserOut])
def list_users(_: dict = Depends(require_admin)):
    return models.list_all_users()


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, req: AdminUserUpdate, admin: dict = Depends(require_admin)):
    user = models.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user["id"] == admin["id"] and (req.role == "user" or req.is_banned):
        raise HTTPException(status_code=400, detail="Admins can't demote or ban themselves")

    fields = {}
    if req.role is not None:
        if req.role not in ("user", "admin"):
            raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")
        fields["role"] = req.role
    if req.is_banned is not None:
        fields["is_banned"] = req.is_banned

    return models.update_user(user, **fields)


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Admins can't delete themselves")
    user = models.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    models.delete_user(user_id)
