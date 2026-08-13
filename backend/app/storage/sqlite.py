"""SQLite 业务数据"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from app.config import settings
from app.models import DocumentInfo, DocumentStatus, SourceType, CaseInfo
from app.utils.logging import log


class SQLiteStore:
    """SQLite 存储 - 业务数据"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or settings.sqlite_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        log.info(f"SQLite 已就绪: {self.db_path}")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        """初始化表结构"""
        with self._conn() as conn:
            # 文档表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    file_path TEXT,
                    size INTEGER DEFAULT 0,
                    chunks_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    error TEXT,
                    uploaded_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            # 案件表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    case_no TEXT UNIQUE,
                    title TEXT NOT NULL,
                    client TEXT,
                    case_type TEXT,
                    amount REAL,
                    court TEXT,
                    status TEXT DEFAULT 'draft',
                    description TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            # 分析结果表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES cases(id)
                )
            """)
            # 用户表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT,
                    role TEXT DEFAULT 'user',
                    avatar_url TEXT,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            # 索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")

    # ===== Document =====
    def upsert_document(self, doc: DocumentInfo):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO documents (id, name, source, file_path, size, chunks_count, status, error, uploaded_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    status=excluded.status,
                    chunks_count=excluded.chunks_count,
                    error=excluded.error,
                    metadata=excluded.metadata
            """, (
                doc.id, doc.name, doc.source.value, doc.file_path,
                doc.size, doc.chunks_count, doc.status.value, doc.error,
                doc.uploaded_at.isoformat(), json.dumps(doc.metadata, ensure_ascii=False, default=str)
            ))

    def get_document(self, doc_id: str) -> Optional[DocumentInfo]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not row:
                return None
            return self._row_to_doc(row)

    def list_documents(self, source: Optional[SourceType] = None, limit: int = 100) -> List[DocumentInfo]:
        with self._conn() as conn:
            if source:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE source = ? ORDER BY uploaded_at DESC LIMIT ?",
                    (source.value, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM documents ORDER BY uploaded_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [self._row_to_doc(r) for r in rows]

    def delete_document(self, doc_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return cur.rowcount > 0

    def _row_to_doc(self, row) -> DocumentInfo:
        return DocumentInfo(
            id=row["id"],
            name=row["name"],
            source=SourceType(row["source"]),
            file_path=row["file_path"],
            size=row["size"],
            chunks_count=row["chunks_count"],
            status=DocumentStatus(row["status"]),
            error=row["error"],
            uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
            metadata=json.loads(row["metadata"] or "{}"),
        )

    # ===== Case =====
    def upsert_case(self, case: CaseInfo):
        with self._conn() as conn:
            case.updated_at = datetime.now()
            conn.execute("""
                INSERT INTO cases (id, case_no, title, client, case_type, amount, court, status, description, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    case_no=excluded.case_no,
                    title=excluded.title,
                    client=excluded.client,
                    case_type=excluded.case_type,
                    amount=excluded.amount,
                    court=excluded.court,
                    status=excluded.status,
                    description=excluded.description,
                    updated_at=excluded.updated_at,
                    metadata=excluded.metadata
            """, (
                case.id, case.case_no, case.title, case.client, case.case_type,
                case.amount, case.court, case.status, case.description,
                case.created_at.isoformat(), case.updated_at.isoformat(),
                json.dumps(case.metadata, ensure_ascii=False)
            ))

    def get_case(self, case_id: str) -> Optional[CaseInfo]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
            if not row:
                return None
            return CaseInfo(
                id=row["id"],
                case_no=row["case_no"],
                title=row["title"],
                client=row["client"] or "",
                case_type=row["case_type"] or "",
                amount=row["amount"],
                court=row["court"],
                status=row["status"],
                description=row["description"] or "",
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                metadata=json.loads(row["metadata"] or "{}"),
            )

    def list_cases(self, limit: int = 100) -> List[CaseInfo]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM cases ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self.get_case(r["id"]) for r in rows]

    def delete_case(self, case_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))
            return cur.rowcount > 0

    # ===== Analysis =====
    def save_analysis(self, analysis_id: str, case_id: str, result: Dict[str, Any]):
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO analyses (id, case_id, result, created_at)
                VALUES (?, ?, ?, ?)
            """, (analysis_id, case_id, json.dumps(result, ensure_ascii=False), datetime.now().isoformat()))

    def get_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "case_id": row["case_id"],
                "result": json.loads(row["result"]),
                "created_at": row["created_at"],
            }

    def list_analyses(self, case_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM analyses WHERE case_id = ? ORDER BY created_at DESC LIMIT ?",
                (case_id, limit)
            ).fetchall()
            return [{
                "id": r["id"],
                "case_id": r["case_id"],
                "result": json.loads(r["result"]),
                "created_at": r["created_at"],
            } for r in rows]

    # ===== User =====
    def create_user(self, user: Dict[str, Any]) -> str:
        """创建用户，返回 user id"""
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO users (id, username, email, password_hash, display_name, role, avatar_url, created_at, last_login_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user["id"],
                user["username"],
                user.get("email"),
                user["password_hash"],
                user.get("display_name") or user["username"],
                user.get("role", "user"),
                user.get("avatar_url"),
                user["created_at"],
                user.get("last_login_at"),
                json.dumps(user.get("metadata") or {}, ensure_ascii=False),
            ))
            return user["id"]

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self._row_to_user(row) if row else None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return self._row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            return self._row_to_user(row) if row else None

    def update_last_login(self, user_id: str, at: str):
        with self._conn() as conn:
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (at, user_id))

    def _row_to_user(self, row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "password_hash": row["password_hash"],
            "display_name": row["display_name"] or row["username"],
            "role": row["role"] or "user",
            "avatar_url": row["avatar_url"],
            "created_at": row["created_at"],
            "last_login_at": row["last_login_at"],
            "metadata": json.loads(row["metadata"] or "{}"),
        }


# 全局实例
db = SQLiteStore()
