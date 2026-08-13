"""
aipath 用户认证服务 - 律瞳委托给 aipath

律瞳的 auth API 不再维护自己的 users 表，而是直接读 aipath 的
career.db 做认证。这样:
- aipath 现有的 11 个用户立即可以在律瞳登录
- 两边 JWT 用同一个 secret + 数字 ID 作 sub，token 完全互通
- 律瞳注册时直接写 aipath 的表（同步生效）

aipath users 表 schema:
  id (INTEGER PK) | username | email | password_hash | display_name
  | avatar_url | role | is_active | created_at (unix ts) | last_login_at (unix ts) | openid
"""
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from app.utils.security import hash_password, verify_password
from app.utils.logging import log


# aipath 数据库路径（可被 .env 覆盖）
DEFAULT_AIPATH_DB = "/opt/aipath-backend/backend/data/career.db"


def get_aipath_db_path() -> str:
    """延迟读取 aipath db 路径，方便测试覆盖"""
    try:
        from app.config import settings
        custom = getattr(settings, "aipath_db_path", None)
        if custom:
            return str(custom)
    except Exception:
        pass
    return DEFAULT_AIPATH_DB


class AipathAuthService:
    """直连 aipath SQLite 做用户认证"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_aipath_db_path()
        if not Path(self.db_path).exists():
            log.warning(f"[aipath-auth] aipath db 不存在: {self.db_path}，登录将不可用")
        else:
            log.info(f"[aipath-auth] 已就绪: {self.db_path}")

    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def get_user_by_id(self, user_id) -> Optional[Dict[str, Any]]:
        try:
            with self._conn() as conn:
                row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
                return self._row_to_user(row) if row else None
        except Exception as e:
            log.error(f"[aipath-auth] get_user_by_id 失败: {e}")
            return None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        try:
            with self._conn() as conn:
                row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
                return self._row_to_user(row) if row else None
        except Exception as e:
            log.error(f"[aipath-auth] get_user_by_username 失败: {e}")
            return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            with self._conn() as conn:
                row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
                return self._row_to_user(row) if row else None
        except Exception as e:
            log.error(f"[aipath-auth] get_user_by_email 失败: {e}")
            return None

    def authenticate(self, lookup: str, password: str) -> Optional[Dict[str, Any]]:
        """支持 username 或 email 登录"""
        user = None
        if "@" in lookup:
            user = self.get_user_by_email(lookup)
        else:
            user = self.get_user_by_username(lookup)
        if not user:
            return None
        # 检查 is_active
        if user.get("is_active") == 0:
            return None
        if not verify_password(password, user.get("password_hash") or ""):
            return None
        return user

    def create_user(
        self,
        username: str,
        password: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """直接写 aipath 的 users 表"""
        if self.get_user_by_username(username):
            raise ValueError("用户名已被占用")
        if email and self.get_user_by_email(email):
            raise ValueError("邮箱已被注册")

        pwd_hash = hash_password(password)
        now_ts = int(time.time())

        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO users (username, email, password_hash, display_name, role, is_active, created_at, last_login_at)
                VALUES (?, ?, ?, ?, 'user', 1, ?, ?)
            """, (username, email, pwd_hash, display_name or username, now_ts, now_ts))
            user_id = cur.lastrowid

        log.info(f"[aipath-auth] 新用户 {username} (id={user_id})")
        return self.get_user_by_id(user_id)

    def update_last_login(self, user_id) -> None:
        try:
            with self._conn() as conn:
                conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (int(time.time()), user_id))
        except Exception as e:
            log.warning(f"[aipath-auth] update_last_login 失败: {e}")

    def _row_to_user(self, row) -> Dict[str, Any]:
        """统一字段为律瞳格式（datetime 转 ISO）"""
        if not row:
            return None
        d = dict(row)
        # 时间戳转 ISO
        for ts_field in ("created_at", "last_login_at"):
            if d.get(ts_field) and isinstance(d[ts_field], (int, float)):
                d[ts_field] = datetime.fromtimestamp(d[ts_field], tz=timezone.utc).isoformat()
        return d


# 全局实例
aipath_auth = AipathAuthService()
