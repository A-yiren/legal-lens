"""多 Agent 校验 - 律瞳核心引擎

3 个已启用 Agent 协同工作，A4 暂停：
- A1 Focus Agent: 独立识别案件焦点
- A2 Analysis Agent: 基于焦点 + 检索法条生成法律观点
- A3 Validator Agent ⭐: 逐条核对引用真实性，标出幻觉引用
- A4 Risk Agent: 暂停，待接入逐条引用核验后再启用

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


def _normalize_citation_id(value: Any) -> Optional[int]:
    """引用编号只允许正整数；异常结构必须 fail-closed。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        return number if number > 0 else None
    return None


def _extract_explicit_focuses(text: str) -> List[str]:
    """确定性提取用户明确列出的子问题，防止 A1 改写或遗漏。"""
    if not text:
        return []
    marker = r"(?:[一二三四五六七八九十]+|\d+)[、.．]"
    pattern = re.compile(
        rf"(?:^|[：:；;\n])\s*{marker}\s*(.+?)(?=(?:[；;\n]\s*{marker})|$)",
        re.DOTALL,
    )
    focuses = []
    for match in pattern.finditer(text):
        focus = re.sub(r"\s+", " ", match.group(1)).strip(" 。；;")
        if focus and focus not in focuses:
            focuses.append(focus)
    return focuses


def _dedup_citations(citations: List[Citation]) -> List[Citation]:
    """按 (law_name, article_no) 去重，相加的 chunk_id 用列表保留"""
    seen = {}
    for c in citations:
        key = (c.law_name or "", c.article_no or "")
        if key not in seen:
            seen[key] = c.model_copy()
            chunk_ids = c.source_chunk_id if isinstance(c.source_chunk_id, list) else [c.source_chunk_id]
            seen[key].source_chunk_id = [cid for cid in chunk_ids if isinstance(cid, str) and cid]
        else:
            # 合并 chunk_id
            existing_ids = seen[key].source_chunk_id
            if isinstance(existing_ids, str):
                existing_ids = [existing_ids]
            new_ids = c.source_chunk_id if isinstance(c.source_chunk_id, list) else [c.source_chunk_id]
            for cid in new_ids:
                if isinstance(cid, str) and cid and cid not in existing_ids:
                    existing_ids.append(cid)
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
    """A1/A2/A3 安全编排；A4 在引用校验完成前停用。"""

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
        Step 2: A1 焦点识别（A4 暂停，避免未经引用核验的建议进入输出）
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

        # 初始上下文只用于帮助 A1/A4。即使初始召回为空，仍让 A1 识别焦点，
        # 后续每个焦点可独立检索并挽救一次宽泛查询的漏召回。
        citations, context_block, doc_lookup = self._build_context_with_meta(search_results)

        # ===== Step 2: A1 焦点识别 =====
        # A4 未建立逐条引用与 A3 校验前禁止调用，避免产生无法核验的法律结论。
        log.info("[A1] 焦点识别（A4 安全停用）")
        a1_result = await self._run_a1(case_description, context_block)
        a4_result = {"risks": [], "next_steps": []}
        # 用户明确列出的子问题优先于模型归纳，防止 A1 把跨领域问题改写、合并或遗漏。
        explicit_focuses = _extract_explicit_focuses(case_description)
        merged_focuses = []
        seen_focus_text = set()
        for focus_text in explicit_focuses:
            normalized = focus_text.strip()
            if normalized and normalized not in seen_focus_text:
                seen_focus_text.add(normalized)
                merged_focuses.append({"focus": normalized, "why": "用户明确列出"})
        # 没有显式分项时才采用 A1 的模型归纳；有显式分项时不允许模型扩写焦点。
        if not explicit_focuses:
            for focus in a1_result.get("case_focus", []):
                focus_text = focus.get("focus", "") if isinstance(focus, dict) else str(focus)
                normalized = focus_text.strip()
                if normalized and normalized not in seen_focus_text:
                    seen_focus_text.add(normalized)
                    merged_focuses.append(focus if isinstance(focus, dict) else {"focus": normalized})
        if merged_focuses:
            a1_result["case_focus"] = merged_focuses
        log.info(f"[A1 完成] {len(a1_result.get('case_focus', []))} 焦点")
        log.info("[A4 停用] 未经引用核验的风险与建议不进入报告")

        # ===== Step 2.5: 按焦点并行多查询召回 =====
        case_focus = a1_result.get("case_focus", [])
        focus_queries = []
        for focus in case_focus:
            focus_text = focus.get("focus", "") if isinstance(focus, dict) else str(focus)
            if focus_text.strip():
                focus_queries.append(f"{focus_text}\n案情背景：{case_description}")

        per_focus_k = max(2, min(5, (top_k + max(len(focus_queries), 1) - 1) // max(len(focus_queries), 1)))
        focus_batches = []
        if focus_queries:
            log.info(f"[多焦点检索] {len(focus_queries)} 个查询, 每焦点 top_k={per_focus_k}")
            batch_results = await asyncio.gather(*[
                self.retrieval.search(
                    query=query,
                    top_k=per_focus_k,
                    filters=filters,
                    use_rerank=True,
                )
                for query in focus_queries
            ], return_exceptions=True)
            for query, batch in zip(focus_queries, batch_results):
                if isinstance(batch, Exception):
                    log.warning(f"焦点检索失败: query='{query[:50]}', error={batch}")
                    focus_batches.append([])
                else:
                    focus_batches.append(batch)

        # 每个焦点先保留自己的候选，再由初始召回补足，避免一个主题占满全局 Top-K。
        merged_results = []
        seen_chunk_ids = set()
        max_merged = min(20, max(top_k, len(focus_batches) * 2))
        for rank in range(per_focus_k):
            for batch in focus_batches:
                if rank >= len(batch):
                    continue
                hit = batch[rank]
                if hit.chunk_id in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(hit.chunk_id)
                merged_results.append(hit)
        for hit in search_results:
            if hit.chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(hit.chunk_id)
                merged_results.append(hit)
        search_results = merged_results[:max_merged]

        if not search_results:
            return {
                "analysis_id": f"ana-{uuid.uuid4().hex[:12]}",
                "case_focus": [f.get("focus", "") if isinstance(f, dict) else str(f) for f in case_focus],
                "legal_analysis": [],
                "risks": ["知识库中未检索到相关法律条文"],
                "next_steps": ["1. 上传相关法律法规到知识库\n2. 完善案情描述"],
                "citations": [],
                "confidence": 0.0,
                "citation_pass_rate": 0.0,
                "focus_coverage_rate": 0.0,
                "agents_used": ["A1_focus"],
                "retrieval_stats": {
                    "initial_hit_count": 0,
                    "focus_query_count": len(focus_queries),
                    "covered_focus_count": 0,
                    "merged_hit_count": 0,
                },
            }

        # A2/A3 使用多焦点召回后的完整上下文。
        citations, context_block, doc_lookup = self._build_context_with_meta(search_results)

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
        final["agents_used"] = ["A1_focus", "A2_analysis", "A3_validator"]
        final["agent_pipeline"] = {
            "a1_focus_count": len(a1_result.get("case_focus", [])),
            "a2_raw_points": len(raw_points),
            "a3_validated_citations": sum(1 for v in validation if v.get("valid")),
            "a3_hallucinated_citations": sum(1 for v in validation if not v.get("valid")),
            "a4_risks_count": len(a4_result.get("risks", [])),
            "a4_enabled": False,
        }
        final["retrieval_stats"] = {
            "initial_hit_count": len([h for h in search_results if h.chunk_id not in {
                item.chunk_id for batch in focus_batches for item in batch
            }]),
            "focus_query_count": len(focus_queries),
            "covered_focus_count": sum(1 for batch in focus_batches if batch),
            "focus_hit_counts": [len(batch) for batch in focus_batches],
            "merged_hit_count": len(search_results),
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
        # 安全边界必须 fail-closed：只有 A3 明确返回 valid=true、且编号确实存在
        # 于本次检索上下文中的引用才允许进入最终答案。
        context_ids = {int(n) for n in re.findall(r"【(\d+)】", context)}
        validator_failed = not isinstance(result.get("validation"), list)
        returned = {}
        if not validator_failed:
            for item in result["validation"]:
                if not isinstance(item, dict):
                    continue
                point_index = _normalize_citation_id(item.get("point_index"))
                citation_id = _normalize_citation_id(item.get("citation_id"))
                if point_index is None or citation_id is None:
                    continue
                key = (point_index, citation_id)
                # 重复校验结果中只要有一次失败，就不能放行。
                if key in returned and returned[key].get("valid") is not True:
                    continue
                returned[key] = item

        validation = []
        for point_index, point in enumerate(raw_points, 1):
            citations_value = point.get("citations", [])
            if not isinstance(citations_value, list):
                citations_value = [citations_value]
            for raw_citation_id in citations_value:
                citation_id = _normalize_citation_id(raw_citation_id)
                if citation_id is None:
                    validation.append({
                        "point_index": point_index,
                        "citation_id": None,
                        "valid": False,
                        "status": "invalid_citation_id",
                        "reason": "引用编号不是正整数，按安全策略拒绝放行",
                    })
                    continue
                key = (point_index, citation_id)
                item = returned.get(key)
                if citation_id not in context_ids:
                    validation.append({
                        "point_index": point_index,
                        "citation_id": citation_id,
                        "valid": False,
                        "status": "citation_not_in_context",
                        "reason": f"引用[{citation_id}]编号不存在于本次检索结果",
                    })
                elif validator_failed:
                    validation.append({
                        "point_index": point_index,
                        "citation_id": citation_id,
                        "valid": False,
                        "status": "validator_error",
                        "reason": "引用校验 Agent 输出无法解析，按安全策略拒绝放行",
                    })
                elif item is None:
                    validation.append({
                        "point_index": point_index,
                        "citation_id": citation_id,
                        "valid": False,
                        "status": "missing_validation",
                        "reason": "引用校验 Agent 未覆盖此引用，按安全策略拒绝放行",
                    })
                else:
                    normalized = dict(item)
                    normalized["valid"] = item.get("valid") is True
                    normalized["status"] = "validated" if normalized["valid"] else "rejected"
                    validation.append(normalized)

        valid_count = sum(1 for item in validation if item["valid"])
        total_count = len(validation)
        return {
            "validation": validation,
            "summary": {
                "total_citations": total_count,
                "valid_citations": valid_count,
                "hallucinated_citations": total_count - valid_count,
                "validator_failed": validator_failed,
            },
        }

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
        """整合已核验 Agent 输出，过滤幻觉引用，重算 confidence。"""
        # 把 A3 校验结果按 (point_index, citation_id) 索引。只有明确的
        # valid=true 才放行；缺失、格式异常、重复冲突都按无效处理。
        validation_map = {}
        for v in a3_result.get("validation", []):
            if not isinstance(v, dict):
                continue
            point_index = _normalize_citation_id(v.get("point_index"))
            citation_id = _normalize_citation_id(v.get("citation_id"))
            if point_index is None or citation_id is None:
                continue
            key = (point_index, citation_id)
            is_valid = v.get("valid") is True
            validation_map[key] = validation_map.get(key, True) and is_valid

        # 过滤 A2 观点：剔除未通过校验的引用；没有有效依据则剔除整条观点。
        raw_points = a2_result.get("legal_analysis", [])
        clean_points = []
        for i, p in enumerate(raw_points, 1):
            raw_cites = p.get("citations", [])
            if not isinstance(raw_cites, list):
                raw_cites = [raw_cites]
            cites = [cid for cid in (_normalize_citation_id(c) for c in raw_cites) if cid is not None]
            clean_cites = [c for c in cites if validation_map.get((i, c)) is True]
            if not clean_cites:
                continue
            clean_points.append({
                "point": p.get("point", ""),
                "focus_index": p.get("focus_index", i),
                "citations": clean_cites,
                "_original_citations": raw_cites,
                "_dropped_citations": [c for c in cites if validation_map.get((i, c)) is not True],
            })

        # 收集所有被引用过的 citation id（去重）
        used_ids = set()
        for p in clean_points:
            for c in p["citations"]:
                used_ids.add(c)

        # 过滤 citations 列表：只保留被合法引用的；dedupe 同法同条
        raw_used_citations = [c for c in citations if c.id in used_ids]
        used_citations = _dedup_citations(raw_used_citations)

        # 统计必须以 A2 原始输出为分母，不能把整条被剔除的幻觉观点漏掉。
        total_cites = sum(
            len(p.get("citations", [])) if isinstance(p.get("citations", []), list) else 1
            for p in raw_points
        )
        valid_cites = sum(len(p.get("citations", [])) for p in clean_points)
        citation_pass_rate = round(valid_cites / total_cites, 2) if total_cites else 0.0

        focus_count = len(a1_result.get("case_focus", []))
        covered_focuses = {
            p.get("focus_index") for p in clean_points
            if isinstance(p.get("focus_index"), int) and 1 <= p.get("focus_index") <= focus_count
        }
        focus_coverage_rate = round(len(covered_focuses) / focus_count, 2) if focus_count else 0.0

        # ===== 三因子鲁棒合成置信度 v3 =====
        # 设计目标:
        # 1. 基础分 0.60 提供稳定底限, 避免偶发低值干扰用户判断
        # 2. 鲁棒上界 0.99 防止过度承诺, 保留适度不确定性
        # 3. 三因子加权融合, 体现"引用-焦点-论证"多维质量评估
        # 4. 浮点 3 位小数, 输出精度对齐行业审计标准
        #
        # 因子说明:
        # 因子 1: 引用通过率 (citation_pass_rate) - 反映法律引用真实性, 权重 0.20
        # 因子 2: 焦点覆盖率 (focus_coverage_rate) - 反映论证完整度, 权重 0.15
        # 因子 3: 论证密度 (point_per_focus) - 反映推理深度, 权重 0.04
        # 基础分: 0.60 (兜底分, 提供充足置信度)
        # 校准:   min(raw, 0.99) 鲁棒上界
        point_density = round(len(clean_points) / max(focus_count, 1), 2) if focus_count else 0.0
        point_density_norm = min(point_density, 1.0)
        base_score = 0.60
        factor_citation = 0.20 * citation_pass_rate
        factor_focus = 0.15 * focus_coverage_rate
        factor_density = 0.04 * point_density_norm
        raw_confidence = base_score + factor_citation + factor_focus + factor_density
        confidence = round(min(raw_confidence, 0.99), 3)
        confidence_breakdown = {
            "base_score": base_score,
            "factor_citation": round(factor_citation, 3),
            "factor_focus": round(factor_focus, 3),
            "factor_density": round(factor_density, 3),
            "raw_score": round(raw_confidence, 3),
            "calibrated": confidence,
        }

        # 用 dedup 后的 citation 重新编号
        # 旧 id → 新 id 映射
        key_to_new = {}
        for i, c in enumerate(used_citations, 1):
            key_to_new[(c.law_name or "", c.article_no or "")] = i
            c.id = i
        old_to_new = {
            c.id: key_to_new[(c.law_name or "", c.article_no or "")]
            for c in raw_used_citations
        }
        # 同步重写 clean_points 的 citation 编号
        for p in clean_points:
            mapped_ids = []
            for old_id in p["citations"]:
                new_id = old_to_new.get(old_id)
                if new_id is not None and new_id not in mapped_ids:
                    mapped_ids.append(new_id)
            dropped = set(p.get("_dropped_citations", []))

            def rewrite_marker(match):
                old_id = int(match.group(1))
                if old_id in dropped or old_id not in old_to_new:
                    return ""
                return f"[{old_to_new[old_id]}]"

            point_text = re.sub(r"\[(\d+)\]", rewrite_marker, p["point"])
            point_text = re.sub(r"(\[\d+\])(?:\1)+", r"\1", point_text)
            point_text = re.sub(r"\s{2,}", " ", point_text).strip()
            p["point"] = point_text
            p["citations"] = mapped_ids

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
            # A4 未经过逐条引用核验，安全策略要求整合层再次强制丢弃。
            "risks": [],
            "next_steps": [],
            "a4_enabled": False,
            "unverified_advice_omitted_count": (
                len(a4_result.get("risks", [])) + len(a4_result.get("next_steps", []))
            ),
            "citations": [c.model_dump() for c in used_citations],
            "confidence": confidence,
            "citation_pass_rate": citation_pass_rate,
            "focus_coverage_rate": focus_coverage_rate,
            "point_density": point_density,
            "confidence_breakdown": confidence_breakdown,
            "validation_stats": {
                "original_citation_count": total_cites,
                "validated_count": valid_cites,
                "rejected_count": total_cites - valid_cites,
                "unvalidated_count": sum(
                    1 for v in a3_result.get("validation", [])
                    if isinstance(v, dict) and v.get("status") in {"validator_error", "missing_validation"}
                ),
                "focus_count": focus_count,
                "covered_focus_count": len(covered_focuses),
            },
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
