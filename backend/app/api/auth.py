"""用户认证 API"""
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.storage.sqlite import db
from app.utils.security import hash_password, verify_password, create_access_token
from app.api.deps import get_current_user
from app.utils.logging import log

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ===== Pydantic Models =====
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=64)
    email: Optional[EmailStr] = None
    display_name: Optional[str] = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    username: str  # 接受 username 或 email
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    display_name: str
    role: str
    avatar_url: Optional[str] = None
    created_at: str
    last_login_at: Optional[str] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ===== Routes =====
@router.post("/register", response_model=TokenOut)
def register(body: RegisterRequest):
    """注册新用户（同时下发 token）"""
    # 检查 username 唯一
    if db.get_user_by_username(body.username):
        raise HTTPException(400, "用户名已被占用")
    # 检查 email 唯一
    if body.email and db.get_user_by_email(str(body.email)):
        raise HTTPException(400, "邮箱已被注册")

    user_id = f"user-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    user_data = {
        "id": user_id,
        "username": body.username,
        "email": str(body.email) if body.email else None,
        "password_hash": hash_password(body.password),
        "display_name": body.display_name or body.username,
        "role": "user",
        "avatar_url": None,
        "created_at": now,
        "last_login_at": now,
        "metadata": {},
    }
    db.create_user(user_data)
    log.info(f"[注册] 新用户: {body.username} ({user_id})")

    token, expires = create_access_token(user_id, {"role": "user", "username": body.username})
    return TokenOut(
        access_token=token,
        expires_in=expires,
        user=UserOut(**{k: user_data[k] for k in UserOut.model_fields if k in user_data}),
    )


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest):
    """登录 — username 或 email"""
    lookup = body.username.strip()
    user = None
    if "@" in lookup:
        user = db.get_user_by_email(lookup)
    else:
        user = db.get_user_by_username(lookup)
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "用户名或密码错误")

    # 更新 last_login
    now_iso = datetime.now(timezone.utc).isoformat()
    db.update_last_login(user["id"], now_iso)
    user["last_login_at"] = now_iso

    log.info(f"[登录] 用户: {user['username']} ({user['id']})")
    token, expires = create_access_token(user["id"], {"role": user["role"], "username": user["username"]})
    return TokenOut(
        access_token=token,
        expires_in=expires,
        user=UserOut(**{k: user[k] for k in UserOut.model_fields if k in user}),
    )


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserOut(**{k: user[k] for k in UserOut.model_fields if k in user})


@router.post("/logout")
def logout(user: dict = Depends(get_current_user)):
    """登出（前端清 localStorage 即可；后端无状态 JWT 不需要服务端动作）"""
    log.info(f"[登出] 用户: {user['username']}")
    return {"ok": True, "message": "已登出"}
