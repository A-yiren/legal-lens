"""用户认证 API - 委托 aipath 共享用户库

律瞳的登录/注册/me/logout 全部委托 aipath_auth，
读 aipath 的 career.db 做认证。这样:
- aipath 现有用户可直接在律瞳登录
- JWT 用同 secret，sub 用 aipath 的数字 ID
- 律瞳注册时同步写 aipath 表

律瞳自己的 users 表保留为"律瞳用户 profile 缓存"（暂未使用）
"""
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.services.aipath_auth import aipath_auth
from app.utils.security import create_access_token
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
    """注册新用户（同步到 aipath 库）"""
    try:
        user = aipath_auth.create_user(
            username=body.username,
            password=body.password,
            email=str(body.email) if body.email else None,
            display_name=body.display_name,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError:
        raise HTTPException(503, "aipath 用户库不可达，请联系管理员")
    except Exception as e:
        log.exception(f"注册失败: {e}")
        raise HTTPException(500, f"注册失败: {str(e)[:200]}")

    # sub 用 aipath 的数字 id（这样律瞳签的 token 在 aipath 也能用）
    token, expires = create_access_token(
        str(user["id"]),
        {"role": user.get("role", "user"), "username": user["username"]},
    )
    return TokenOut(
        access_token=token,
        expires_in=expires,
        user=_to_user_out(user),
    )


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest):
    """登录 — username 或 email（在 aipath 库里查）"""
    lookup = body.username.strip()
    user = aipath_auth.authenticate(lookup, body.password)
    if not user:
        raise HTTPException(401, "用户名或密码错误")

    aipath_auth.update_last_login(user["id"])

    log.info(f"[登录] {user['username']} (id={user['id']})")
    token, expires = create_access_token(
        str(user["id"]),
        {"role": user.get("role", "user"), "username": user["username"]},
    )
    return TokenOut(
        access_token=token,
        expires_in=expires,
        user=_to_user_out(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息（从 aipath 库）"""
    # user 是 aipath 库返回的 dict（get_current_user 通过 aipath_auth 取）
    return _to_user_out(user)


@router.post("/logout")
def logout(user: dict = Depends(get_current_user)):
    """登出（前端清 localStorage 即可；JWT 无状态）"""
    log.info(f"[登出] {user.get('username')} (id={user.get('id')})")
    return {"ok": True, "message": "已登出"}


# ===== Helpers =====
def _to_user_out(user: dict) -> UserOut:
    return UserOut(
        id=str(user["id"]),
        username=user["username"],
        email=user.get("email"),
        display_name=user.get("display_name") or user["username"],
        role=user.get("role") or "user",
        avatar_url=user.get("avatar_url"),
        created_at=str(user.get("created_at") or ""),
        last_login_at=user.get("last_login_at"),
    )
