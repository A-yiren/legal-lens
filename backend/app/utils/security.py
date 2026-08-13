"""
安全工具 — 密码 hash + JWT
格式与 aipath 一致 (bcrypt + HS256 + 72h)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Union

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# bcrypt（直接用 passlib 的 wrapper 简化）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """bcrypt 限制 72 字节，先截断再 hash（与 aipath 一致）"""
    pwd = plain.encode("utf-8")[:72]
    return pwd_context.hash(pwd)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pwd = plain.encode("utf-8")[:72]
        return pwd_context.verify(pwd, hashed)
    except Exception:
        return False


def create_access_token(subject: Union[str, int], extra: Optional[Dict[str, Any]] = None) -> tuple:
    """返回 (token, expires_in_seconds)"""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, settings.jwt_expire_hours * 3600


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}")
