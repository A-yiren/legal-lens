"""生成服务 - 委托给多 Agent 编排器 (agents.MultiAgentOrchestrator)

保留旧 API 兼容，但内部走多 Agent 校验流程：
- A1 焦点识别 Agent
- A2 法律分析 Agent
- A3 引用校验 Agent ⭐
- A4 风险评估 Agent
"""
import uuid
from typing import List, Dict, Any, Optional
from app.models import Citation
from app.services.llm import llm_service
from app.services.retrieval import retrieval_service
from app.services.agents import multi_agent
from app.storage.sqlite import db
from app.utils.logging import log

# 保留旧 SYSTEM_PROMPT 仅供 answer_question 用
SYSTEM_PROMPT = """你是【律瞳】，一位专业的律师助理 AI。你的任务是基于检索到的真实法律条文，为律师的案件提供结构化分析参考。

# 严格规则（不可违反）

1. **只基于检索到的条文回答**：所有法律观点必须从【法律条文】部分引用，不可凭空编造任何法条；不可引用知识库检索之外的"记忆法条"
2. **强制引用标注**：每一条法律观点后必须用 [1][2][3] 这样的编号标注引用，不可遗漏；引用编号必须存在于【法律条文】列表中
3. **引用真实性校验**：每条引用 [n] 必须在【法律条文】的对应编号中存在；若你无法从【法律条文】中找到支持某观点的具体条文，请删除该观点或将其置信度调低
4. **不可回答的情况**：如果检索到的条文不足以回答问题，明确说明"现有知识库暂无法支持该分析"，不要瞎猜或套用其他无关法条
5. **不替代律师**：这是辅助分析工具，最终法律意见由执业律师作出
6. **结构化输出**：严格按 JSON 格式输出

# 时效与版本声明

每条引用 [n] 对应的法条，应尽可能反映其最新有效版本。如某法条有多个修正版本，优先使用知识库中"最新生效"版本。每条回答末尾可注明"本回答基于知识库第X次更新（约 YYYY-MM-DD）"。

# 输出 JSON Schema

```json
{
  "case_focus": ["案件焦点1", "案件焦点2"],
  "legal_analysis": [
    {"point": "法律观点1", "citations": [1, 2]},
    {"point": "法律观点2", "citations": [3]}
  ],
  "risks": ["风险点1", "风险点2"],
  "next_steps": ["下一步建议1", "下一步建议2"],
  "confidence": 0.85,
  "disclaimer": "本回答基于律瞳知识库检索结果，最终意见以执业律师及官方法律文本为准"
}
```

请严格按上述 JSON 格式输出，只输出 JSON 本身，不要任何解释性文字。"""


class GenerationService:
    """RAG 生成服务（多 Agent 调度版）"""

    def __init__(self):
        self.retrieval = retrieval_service
        self.llm = llm_service
        self.orchestrator = multi_agent  # 多 Agent 编排器

    async def analyze(
        self,
        case_description: str,
        case_id: Optional[str] = None,
        top_k: int = 12,
        filters: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """案件分析 - 多 Agent 校验

        Returns:
            {
                "analysis_id": "...",
                "case_focus": [...],
                "legal_analysis": [...],
                "risks": [...],
                "next_steps": [...],
                "citations": [{id, law_name, article_no, source_url, ...}],
                "confidence": 0.85,
                "agents_used": ["A1_focus", "A2_analysis", "A3_validator", "A4_risk"],
                "agent_pipeline": {...}
            }
        """
        log.info(f"[多 Agent 分析] case_id={case_id}, desc_len={len(case_description)}")

        # 委托给多 Agent 编排器
        analysis = await self.orchestrator.analyze(
            case_description=case_description,
            case_id=case_id,
            top_k=top_k,
            filters=filters,
        )

        # 保存到 SQLite
        if case_id and analysis.get("analysis_id"):
            db.save_analysis(analysis["analysis_id"], case_id, analysis)

        return analysis

    def _build_context(self, search_results: List) -> tuple[List[Citation], str]:
        """构造 LLM 上下文：引用列表 + 格式化文本"""
        citations = []
        lines = []

        for i, r in enumerate(search_results, 1):
            citation = Citation(
                id=i,
                law_name=r.law_name or "未知名法律",
                article_no=r.article_no or "",
                article_text=r.text,
                source_chunk_id=r.chunk_id,
                similarity=r.score,
            )
            citations.append(citation)
            lines.append(
                f"【{i}】{citation.law_name} {citation.article_no}\n"
                f"{r.text}\n"
                f"(相关度: {r.score:.3f})"
            )

        return citations, "\n\n".join(lines)

    def _parse_llm_result(
        self,
        llm_result: Dict[str, Any],
        citations: List[Citation],
        search_results: List,
    ) -> Dict[str, Any]:
        """解析 LLM 输出，构造最终结果"""
        if not llm_result:
            # LLM 失败时的降级
            return {
                "case_focus": ["AI 分析暂时不可用"],
                "legal_analysis": [
                    {"point": f"参考条文 {c.law_name} {c.article_no}: {c.article_text[:100]}...",
                     "citations": [c.id]}
                    for c in citations[:3]
                ],
                "risks": ["AI 服务暂不可用，请稍后重试或人工分析"],
                "next_steps": ["1. 重新尝试 AI 分析\n2. 人工查阅上述参考条文"],
                "citations": [c.model_dump() for c in citations],
                "confidence": 0.0,
            }

        # 解析 LLM 输出
        result = {
            "case_focus": llm_result.get("case_focus", []),
            "legal_analysis": llm_result.get("legal_analysis", []),
            "risks": llm_result.get("risks", []),
            "next_steps": llm_result.get("next_steps", []),
            "confidence": float(llm_result.get("confidence", 0.7)),
            "citations": [c.model_dump() for c in citations],
        }

        # 补充 win_probability（如果 LLM 给出了胜诉可能性）
        if "win_probability" in llm_result:
            result["win_probability"] = llm_result["win_probability"]

        return result

    async def answer_question(
        self,
        question: str,
        case_id: Optional[str] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """简单问答：用户提问 → 检索 → LLM 回答"""
        search_results = await self.retrieval.search(question, top_k=top_k)
        if not search_results:
            return {
                "answer": "抱歉，知识库中未找到相关信息。",
                "citations": [],
            }

        citations, context_block = self._build_context(search_results)
        user_msg = f"问题：{question}\n\n相关法律条文：\n{context_block}\n\n请基于上述条文简洁回答问题，并标注引用编号。"

        answer = await self.llm.chat(
            system="你是律师助理 AI，基于检索到的法律条文回答问题。每条观点必须标注引用 [1][2]...",
            user=user_msg,
            temperature=0.3,
            max_tokens=2000,
        )

        return {
            "answer": answer,
            "citations": [c.model_dump() for c in citations],
        }


# 全局实例
generation_service = GenerationService()
