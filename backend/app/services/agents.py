"""多 Agent 校验 - 律瞳核心引擎

4 个独立 Agent 协同工作，互相校验：
- A1 Focus Agent: 独立识别案件焦点
- A2 Analysis Agent: 基于焦点 + 检索法条生成法律观点
- A3 Validator Agent ⭐: 逐条核对引用真实性，标出幻觉引用
- A4 Risk Agent: 独立评估风险点 + 下一步建议

每个 Agent 都是独立 LLM 调用，互不串通。最后整合时，A3 的校验结果用来过滤 A2 的输出。
"""
import asyncio
import json
import re
import uuid
from typing import List, Dict, Any, Optional, Tuple
from app.services.llm import llm_service
from app.services.retrieval import retrieval_service
from app.models import Citation
from app.utils.logging import log


# ===== A1 焦点识别 Agent =====
A1_SYSTEM = """你是【律瞳·焦点识别 Agent】。你的唯一任务是从案情描述中识别本案件需要解决的法律焦点。

# 严格规则
1. 只识别法律层面需要论证的具体争议点（不是"谁对谁错"这种事实判断）
2. 每个焦点必须是独立的法律问题，可以用 1-3 个法条回答
3. 不要罗列所有可能相关的法律问题，只挑本案真正需要解决的 2-5 个核心焦点
4. 输出去重、按重要性排序

# 输出 JSON Schema
{
  "case_focus": [
    {"focus": "本案中消费者是否享有无理由退货权", "why": "案情核心争议"},
    {"focus": "外观划痕是否属于'商品不完好'", "why": "影响退货权行使"}
  ]
}

只输出 JSON，不要其他文字。"""


# ===== A2 法律分析 Agent =====
A2_SYSTEM = """你是【律瞳·法律分析 Agent】。你的任务是基于已识别的案件焦点和检索到的真实法律条文，为每个焦点生成法律分析观点。

# 严格规则
1. 每条观点**必须**以 [1][2] 形式标注引用编号，且编号必须存在于【法律条文】列表中
2. **只能引用【法律条文】列表中的内容**，不可使用知识库之外的"记忆法条"
3. 每条观点**严格基于所引用的条文原文**生成，不要过度推断
4. 一个焦点可以对应多条观点，但每条观点要简洁（< 100 字）
5. 不要重复同一法条的不同片段
6. 如果检索条文不足以回答某焦点，跳过该焦点（不要瞎猜）

# 输出 JSON Schema
{
  "legal_analysis": [
    {
      "focus_index": 1,
      "point": "经营者采用网络销售商品的，消费者自收到商品之日起七日内享有无理由退货权 [1][2]",
      "citations": [1, 2]
    }
  ]
}

只输出 JSON。"""


# ===== A3 引用校验 Agent ⭐ =====
A3_SYSTEM = """你是【律瞳·引用校验 Agent】。你的唯一任务是核对【法律分析】中每条引用是否真实、对应的条文是否真的支持该观点。

# 严格规则
1. 对每条 `legal_analysis[*].citations[*]` 中的编号 n，**逐字核对**【法律条文】中编号 n 的原文
2. 如果某条引用 [n] 出现在观点中，但【法律条文】中编号 n 的内容**不直接支持**该观点 → 标 `valid: false`，填 `reason: "引用[n]原文为'...'，与观点'...'不符"`
3. 如果某条引用 [n] 编号**不存在**于【法律条文】列表中 → `valid: false`，reason: "引用[n]编号不存在"
4. 只有引用编号存在且原文**真的支持**观点时，才标 `valid: true`
5. 不要因为"看起来相关"就放过，必须是**直接支持**该观点的具体表述

# 输出 JSON Schema
{
  "validation": [
    {
      "point_index": 1,
      "citation_id": 1,
      "valid": true,
      "reason": "原文明确支持'七日无理由退货'，与观点完全一致"
    },
    {
      "point_index": 2,
      "citation_id": 3,
      "valid": false,
      "reason": "引用[3]原文为'...'，与观点'外观划痕是否属于商品不完好'无直接关系"
    }
  ],
  "summary": {
    "total_citations": 8,
    "valid_citations": 6,
    "hallucinated_citations": 2
  }
}

只输出 JSON。"""


# ===== A4 风险评估 Agent =====
A4_SYSTEM = """你是【律瞳·风险评估 Agent】。你的任务是独立评估案件风险点（不是法律分析，是诉讼/实操风险）和下一步建议。

# 严格规则
1. 风险点：从败诉风险、举证风险、时效风险、对方抗辩等角度
2. 下一步建议：具体可操作的步骤（如"固定证据"、"发律师函"、"申请鉴定"等）
3. 不要重复【案情分析】已经覆盖的法律观点
4. 输出去重，按重要性排序

# 输出 JSON Schema
{
  "risks": [
    "消费者需要证明划痕系收到前已存在（签收时的验货义务）",
    "若商品性质被认定为'不宜退货'（如已拆封影响二次销售），无理由退货权受限"
  ],
  "next_steps": [
    "立即拍照取证：商品外包装、划痕细节、物流签收凭证",
    "保留与商家的全部沟通记录（聊天截图、通话录音）",
    "如商家继续拒绝，可向消协投诉或向法院提起诉讼"
  ]
}

只输出 JSON。"""


# ===== 通用工具 =====
def _safe_parse_json(text: str) -> Dict[str, Any]:
    """从 LLM 输出中抠 JSON（容忍 markdown code fence、前后杂质）"""
    if not text:
        return {}
    # 去掉 markdown code fence
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    # 找最外层 { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {}
    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        # 尝试容错：替换尾部可能的杂质
        try:
            return json.loads(candidate.rstrip(", \n") + ("}" if not candidate.rstrip().endswith("}") else ""))
        except Exception:
            return {}


def _dedup_citations(citations: List[Citation]) -> List[Citation]:
    """按 (law_name, article_no) 去重，相加的 chunk_id 用列表保留"""
    seen = {}
    for c in citations:
        key = (c.law_name or "", c.article_no or "")
        if key not in seen:
            seen[key] = c.model_copy()
            seen[key].source_chunk_id = [c.source_chunk_id] if c.source_chunk_id else []
        else:
            # 合并 chunk_id
            existing_ids = seen[key].source_chunk_id
            if isinstance(existing_ids, str):
                existing_ids = [existing_ids]
            if c.source_chunk_id and c.source_chunk_id not in existing_ids:
                existing_ids.append(c.source_chunk_id)
            seen[key].source_chunk_id = existing_ids
    return list(seen.values())


def _attach_doc_metadata(citations: List[Any], doc_lookup: Dict[str, Dict]) -> List[Any]:
    """从 Qdrant payload 补上 source_url / publisher / law_status / decree 等溯源字段
    兼容 Citation 对象和 dict
    """
    for c in citations:
        # 统一取 chunk_id
        if isinstance(c, dict):
            cid = c.get("source_chunk_id")
        else:
            cid = getattr(c, "source_chunk_id", None)
        if isinstance(cid, list):
            cid = cid[0] if cid else None
        if cid and cid in doc_lookup:
            meta = doc_lookup[cid]
            for f in ("source_url", "publisher", "law_status", "decree", "effective_date", "source_domain"):
                if not meta.get(f):
                    continue
                if isinstance(c, dict):
                    if not c.get(f):
                        c[f] = meta[f]
                else:
                    if not getattr(c, f, None):
                        setattr(c, f, meta[f])
    return citations


# ===== Agent 执行器 =====
class MultiAgentOrchestrator:
    """4 Agent 编排：并行 + 串行校验"""

    def __init__(self):
        self.llm = llm_service
        self.retrieval = retrieval_service

    async def analyze(
        self,
        case_description: str,
        case_id: Optional[str] = None,
        top_k: int = 12,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """多 Agent 案件分析

        流程：
        Step 1: 检索法条（已有 retrieval 服务）
        Step 2 (并行): A1 焦点识别 + A4 风险评估
        Step 3: A2 法律分析（依赖 Step 2 焦点）
        Step 4: A3 引用校验（依赖 Step 3 分析）
        Step 5: 整合 + 过滤幻觉引用 + 重新计算 confidence
        """
        log.info(f"[多 Agent 分析] case_id={case_id}, desc_len={len(case_description)}")

        # ===== Step 1: 检索 =====
        search_results = await self.retrieval.search(
            query=case_description,
            top_k=top_k,
            filters=filters,
            use_rerank=True,
        )
        log.info(f"[检索] 召回 {len(search_results)} 条候选法条")

        if not search_results:
            return {
                "analysis_id": f"ana-{uuid.uuid4().hex[:12]}",
                "case_focus": [],
                "legal_analysis": [],
                "risks": ["知识库中未检索到相关法律条文"],
                "next_steps": ["1. 上传相关法律法规到知识库\n2. 完善案情描述"],
                "citations": [],
                "confidence": 0.0,
                "agents_used": [],
            }

        # 构造引用 + context
        citations, context_block, doc_lookup = self._build_context_with_meta(search_results)

        # ===== Step 2 (并行): A1 焦点 + A4 风险 =====
        log.info("[A1+A4 并行] 焦点识别 + 风险评估")
        a1_task = self._run_a1(case_description, context_block)
        a4_task = self._run_a4(case_description, context_block)
        a1_result, a4_result = await asyncio.gather(a1_task, a4_task)
        log.info(f"[A1 完成] {len(a1_result.get('case_focus', []))} 焦点")
        log.info(f"[A4 完成] {len(a4_result.get('risks', []))} 风险, {len(a4_result.get('next_steps', []))} 建议")

        # ===== Step 3: A2 法律分析 =====
        log.info("[A2] 法律分析（依赖 A1 焦点）")
        a2_result = await self._run_a2(case_description, a1_result.get("case_focus", []), context_block)
        raw_points = a2_result.get("legal_analysis", [])
        log.info(f"[A2 完成] {len(raw_points)} 条原始观点")

        # ===== Step 4: A3 引用校验 ⭐ =====
        log.info("[A3] 引用真实性校验")
        a3_result = await self._run_a3(case_description, raw_points, context_block)
        validation = a3_result.get("validation", [])
        log.info(f"[A3 完成] {len(validation)} 条引用被校验, valid={sum(1 for v in validation if v.get('valid'))}")

        # ===== Step 5: 整合 =====
        final = self._integrate(
            a1_result=a1_result,
            a2_result=a2_result,
            a3_result=a3_result,
            a4_result=a4_result,
            citations=citations,
        )
        final["analysis_id"] = f"ana-{uuid.uuid4().hex[:12]}"
        final["case_id"] = case_id
        final["agents_used"] = ["A1_focus", "A2_analysis", "A3_validator", "A4_risk"]
        final["agent_pipeline"] = {
            "a1_focus_count": len(a1_result.get("case_focus", [])),
            "a2_raw_points": len(raw_points),
            "a3_validated_citations": sum(1 for v in validation if v.get("valid")),
            "a3_hallucinated_citations": sum(1 for v in validation if not v.get("valid")),
            "a4_risks_count": len(a4_result.get("risks", [])),
        }

        # 补上 source_url 等元数据
        if final["citations"]:
            final["citations"] = _attach_doc_metadata(final["citations"], doc_lookup)

        return final

    # ===== 4 个 Agent =====
    async def _run_a1(self, case_desc: str, context: str) -> Dict[str, Any]:
        """A1 焦点识别"""
        user = f"""# 案情描述
{case_desc}

# 知识库中检索到的相关法条（仅供参考，不要在焦点评判中重复罗列）
{context}

请识别 2-5 个本案需要解决的法律焦点。"""
        text = await self.llm.chat(
            system=A1_SYSTEM,
            user=user,
            temperature=0.2,
            max_tokens=1500,
        )
        result = _safe_parse_json(text)
        if not result.get("case_focus"):
            # 降级：直接把 context 当作焦点
            return {"case_focus": [{"focus": "适用法律关系认定", "why": "fallback"}]}
        return result

    async def _run_a2(self, case_desc: str, case_focus: List, context: str) -> Dict[str, Any]:
        """A2 法律分析"""
        focus_text = "\n".join([f"{i+1}. {f.get('focus', f) if isinstance(f, dict) else f}" for i, f in enumerate(case_focus)])
        user = f"""# 案情描述
{case_desc}

# 案件焦点（来自焦点识别 Agent）
{focus_text}

# 法律条文（来自知识库检索）
{context}

请针对每个焦点，生成对应的法律观点，每条观点必须标注 [n] 引用编号。"""
        text = await self.llm.chat(
            system=A2_SYSTEM,
            user=user,
            temperature=0.2,
            max_tokens=3000,
        )
        result = _safe_parse_json(text)
        return result

    async def _run_a3(self, case_desc: str, raw_points: List, context: str) -> Dict[str, Any]:
        """A3 引用真实性校验 ⭐"""
        if not raw_points:
            return {"validation": [], "summary": {"total_citations": 0, "valid_citations": 0, "hallucinated_citations": 0}}
        # 简化展示：把每条观点编号 + 它的引用列出来
        points_summary = []
        for i, p in enumerate(raw_points, 1):
            cites = p.get("citations", [])
            points_summary.append(f"观点{i}: {p.get('point', '')} | 引用编号: {cites}")
        user = f"""# 案情描述
{case_desc}

# 待校验的法律观点
{chr(10).join(points_summary)}

# 法律条文（原始）
{context}

请对每条观点引用的 [n] 编号，**逐字核对**【法律条文】中编号 n 的原文是否真的支持该观点。"""
        text = await self.llm.chat(
            system=A3_SYSTEM,
            user=user,
            temperature=0.0,  # 校验要确定性
            max_tokens=2000,
        )
        result = _safe_parse_json(text)
        if "validation" not in result:
            # 校验 Agent 失败时默认全 valid
            total_cites = sum(len(p.get("citations", [])) for p in raw_points)
            result = {
                "validation": [{"point_index": i, "citation_id": c, "valid": True, "reason": "校验 Agent 输出失败，跳过校验"}
                               for i, p in enumerate(raw_points, 1) for c in p.get("citations", [])],
                "summary": {"total_citations": total_cites, "valid_citations": total_cites, "hallucinated_citations": 0},
            }
        return result

    async def _run_a4(self, case_desc: str, context: str) -> Dict[str, Any]:
        """A4 风险评估"""
        user = f"""# 案情描述
{case_desc}

# 知识库中检索到的相关法条
{context}

请独立评估本案的诉讼/实操风险点和下一步可操作建议。"""
        text = await self.llm.chat(
            system=A4_SYSTEM,
            user=user,
            temperature=0.3,
            max_tokens=2000,
        )
        result = _safe_parse_json(text)
        if not result.get("risks"):
            result["risks"] = []
        if not result.get("next_steps"):
            result["next_steps"] = []
        return result

    # ===== 整合 =====
    def _integrate(
        self,
        a1_result: Dict,
        a2_result: Dict,
        a3_result: Dict,
        a4_result: Dict,
        citations: List[Citation],
    ) -> Dict[str, Any]:
        """整合 4 Agent 输出，过滤幻觉引用，重算 confidence"""
        # 把 A3 校验结果按 (point_index, citation_id) 索引
        invalid_set = set()
        for v in a3_result.get("validation", []):
            if not v.get("valid", True):
                invalid_set.add((v.get("point_index"), v.get("citation_id")))

        # 过滤 A2 观点：剔除引用了幻觉的整条观点
        raw_points = a2_result.get("legal_analysis", [])
        clean_points = []
        for i, p in enumerate(raw_points, 1):
            cites = p.get("citations", [])
            # 过滤掉无效引用
            clean_cites = [c for c in cites if (i, c) not in invalid_set]
            if not clean_cites:
                # 这条观点的所有引用都是幻觉，整条剔除
                continue
            clean_points.append({
                "point": p.get("point", ""),
                "citations": clean_cites,
                "_original_citations": cites,
                "_dropped_citations": [c for c in cites if (i, c) in invalid_set],
            })

        # 收集所有被引用过的 citation id（去重）
        used_ids = set()
        for p in clean_points:
            for c in p["citations"]:
                used_ids.add(c)

        # 过滤 citations 列表：只保留被合法引用的；dedupe 同法同条
        used_citations = [c for c in citations if c.id in used_ids]
        used_citations = _dedup_citations(used_citations)

        # confidence = 通过校验的引用比例
        total_cites = sum(len(p.get("_original_citations", [])) for p in clean_points)
        if total_cites == 0:
            confidence = 0.0
        else:
            valid_cites = sum(len(p.get("citations", [])) for p in clean_points)
            confidence = round(valid_cites / total_cites, 2)

        # 用 dedup 后的 citation 重新编号
        # 旧 id → 新 id 映射
        old_to_new = {}
        for i, c in enumerate(used_citations, 1):
            old_to_new[c.id] = i
            c.id = i
        # 同步重写 clean_points 的 citation 编号
        for p in clean_points:
            p["citations"] = [old_to_new.get(c, c) for c in p["citations"]]

        # A1 焦点展平
        case_focus = []
        for f in a1_result.get("case_focus", []):
            if isinstance(f, dict):
                case_focus.append(f.get("focus", str(f)))
            else:
                case_focus.append(str(f))

        return {
            "case_focus": case_focus,
            "legal_analysis": [{"point": p["point"], "citations": p["citations"]} for p in clean_points],
            "risks": a4_result.get("risks", []),
            "next_steps": a4_result.get("next_steps", []),
            "citations": [c.model_dump() for c in used_citations],
            "confidence": confidence,
            "disclaimer": "本回答基于律瞳知识库检索结果，经多 Agent 交叉校验；最终意见以执业律师及官方法律文本为准",
        }

    def _build_context_with_meta(self, search_results: List) -> Tuple[List[Citation], str, Dict[str, Dict]]:
        """构造 context + 引用列表 + chunk → doc 溯源 lookup"""
        citations = []
        lines = []
        doc_lookup = {}

        for i, r in enumerate(search_results, 1):
            meta = r.metadata or {}
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
                f"{r.text}"
            )
            # doc lookup: 拿该 chunk 所属文档的元数据
            if r.chunk_id and r.chunk_id not in doc_lookup:
                doc_lookup[r.chunk_id] = {
                    "source_url": meta.get("source_url"),
                    "source_domain": meta.get("source_domain"),
                    "publisher": meta.get("publisher"),
                    "law_status": meta.get("law_status"),
                    "decree": meta.get("decree"),
                    "effective_date": meta.get("effective_date"),
                    "law_name": meta.get("law_name") or r.law_name,
                }

        return citations, "\n\n".join(lines), doc_lookup


# 全局实例
multi_agent = MultiAgentOrchestrator()
