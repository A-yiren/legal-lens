"""类案 + 合同审查 API"""
import json
from typing import Optional, List
from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from app.services.case_retrieval import case_retrieval
from app.services.contract_review import contract_reviewer
from app.storage.sqlite import db
from app.utils.logging import log

router = APIRouter(prefix="/api", tags=["cases"])


class CaseSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    cause: Optional[str] = None
    court_level: Optional[str] = None


class ContractReviewRequest(BaseModel):
    contract_text: str
    contract_type: str = "general"  # general/labor/sale/lease/service
    user_role: str = "中立"  # 我方/对方/中立


@router.get("/cases")
async def list_cases(
    status: Optional[str] = Query(None, description="按状态过滤: draft/processing/done/closed"),
    search: Optional[str] = Query(None, description="按案件名称/案号/客户模糊搜索"),
    limit: int = Query(200, ge=1, le=500),
):
    """列出所有用户案件（案件库页面用）"""
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    sql = "SELECT id, case_no, title, client, case_type, amount, court, status, description, created_at, updated_at, metadata FROM cases WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if search:
        sql += " AND (title LIKE ? OR case_no LIKE ? OR client LIKE ?)"
        kw = f"%{search}%"
        params.extend([kw, kw, kw])
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = c.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/cases/search")
async def search_cases(req: CaseSearchRequest):
    """类案检索"""
    try:
        results = await case_retrieval.search_similar_cases(
            query=req.query,
            top_k=req.top_k,
            cause=req.cause,
            court_level=req.court_level,
        )
        return {
            "query": req.query,
            "total": len(results),
            "results": [r.model_dump() for r in results],
        }
    except Exception as e:
        log.exception(f"类案检索失败: {e}")
        raise HTTPException(500, f"类案检索失败: {str(e)[:200]}")


@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    """获取案件详情"""
    case = await case_retrieval.get_case(case_id)
    if not case:
        raise HTTPException(404, "案件不存在")
    return case


@router.post("/contract/review")
async def review_contract(req: ContractReviewRequest):
    """合同审查"""
    if not req.contract_text.strip():
        raise HTTPException(400, "合同内容不能为空")
    if len(req.contract_text) > 50000:
        raise HTTPException(400, "合同内容过长（>50000 字符）")
    try:
        result = await contract_reviewer.review(
            contract_text=req.contract_text,
            contract_type=req.contract_type,
            user_role=req.user_role,
        )
        return result
    except Exception as e:
        log.exception(f"合同审查失败: {e}")
        raise HTTPException(500, f"合同审查失败: {str(e)[:200]}")
