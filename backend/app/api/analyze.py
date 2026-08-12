"""案件分析 API"""
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import StreamingResponse

from app.services.generation import generation_service
from app.storage.sqlite import db
from app.utils.logging import log


router = APIRouter(prefix="/api/analyze", tags=["analyze"])


@router.post("")
async def analyze_case(
    case_description: str = Body(..., embed=True),
    case_id: Optional[str] = Body(None, embed=True),
    top_k: int = Body(8, embed=True),
    filters: Optional[dict] = Body(None, embed=True),
    stream: bool = Body(False, embed=True),
):
    """案件分析

    RAG 全流程：案情 → 检索 → LLM 生成 → 引用
    """
    if not case_description.strip():
        raise HTTPException(400, "案情描述不能为空")

    if stream:
        # 流式输出
        async def event_stream():
            try:
                result = await generation_service.analyze(
                    case_description=case_description,
                    case_id=case_id,
                    top_k=top_k,
                    filters=filters,
                    stream=False,  # generation.analyze 内部不分流
                )
                # 按 JSON chunks 推
                yield f"data: {json.dumps({'type': 'meta', 'citations': result.get('citations', [])}, ensure_ascii=False)}\n\n"
                # 推送主体
                yield f"data: {json.dumps({'type': 'result', **result}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                log.exception(f"流式分析失败: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    else:
        # 同步输出
        try:
            result = await generation_service.analyze(
                case_description=case_description,
                case_id=case_id,
                top_k=top_k,
                filters=filters,
            )
            return result
        except Exception as e:
            log.exception(f"分析失败: {e}")
            raise HTTPException(500, f"分析失败: {e}")


@router.post("/ask")
async def ask_question(
    question: str = Body(..., embed=True),
    case_id: Optional[str] = Body(None, embed=True),
    top_k: int = Body(5, embed=True),
):
    """简单问答"""
    if not question.strip():
        raise HTTPException(400, "问题不能为空")

    try:
        result = await generation_service.answer_question(
            question=question,
            case_id=case_id,
            top_k=top_k,
        )
        return result
    except Exception as e:
        log.exception(f"问答失败: {e}")
        raise HTTPException(500, f"问答失败: {e}")


@router.get("/{analysis_id}")
async def get_analysis(analysis_id: str):
    """获取分析结果"""
    result = db.get_analysis(analysis_id)
    if not result:
        raise HTTPException(404, "分析结果不存在")
    return result


@router.get("/by-case/{case_id}")
async def list_case_analyses(case_id: str, limit: int = 20):
    """列出某案件的所有分析"""
    results = db.list_analyses(case_id, limit=limit)
    return results
