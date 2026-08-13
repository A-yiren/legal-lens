"""FastAPI 公共依赖"""
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.storage.sqlite import db
from app.utils.security import decode_token

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """从 Authorization: Bearer <jwt> 解析当前用户"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token 无效: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 缺少 subject")
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """可选登录 — 没 token 返回 None 而非 401（用于公开 + 登录后增强体验的端点）"""
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub")
        if user_id:
            return db.get_user_by_id(user_id)
    except Exception:
        pass
    return None
