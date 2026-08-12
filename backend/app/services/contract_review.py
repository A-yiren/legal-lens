"""合同审查服务 - 规则引擎 + RAG

核心能力：
1. 风险条款识别（基于规则模板）
2. 缺失条款识别（必备条款检查）
3. 引用法条支持（RAG 检索）
4. 修改建议生成（LLM）
"""
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from app.services.llm import llm_service
from app.services.retrieval import retrieval_service
from app.utils.logging import log


# ===== 必备条款模板（按合同类型）=====
CONTRACT_REQUIRED_CLAUSES = {
    "general": [
        {"key": "parties", "name": "当事人信息", "description": "合同双方完整的主体信息（名称、地址、统一社会信用代码）"},
        {"key": "subject", "name": "标的条款", "description": "合同标的物的明确描述"},
        {"key": "quantity_quality", "name": "数量与质量", "description": "标的物的数量、质量标准"},
        {"key": "price_payment", "name": "价款与支付", "description": "金额、支付方式、付款时间"},
        {"key": "delivery", "name": "履行期限、地点、方式", "description": "明确履行的时间、地点、方式"},
        {"key": "breach", "name": "违约责任", "description": "违约情形及违约金计算方式"},
        {"key": "dispute_resolution", "name": "争议解决", "description": "诉讼或仲裁管辖约定"},
        {"key": "force_majeure", "name": "不可抗力", "description": "不可抗力情形及处理方式"},
        {"key": "effective_termination", "name": "生效与终止", "description": "合同生效条件、终止条件"},
        {"key": "signature_date", "name": "签字盖章与日期", "description": "双方签字盖章及签订日期"},
    ],
    "labor": [
        {"key": "parties", "name": "双方信息", "description": "用人单位与劳动者的完整信息"},
        {"key": "term", "name": "合同期限", "description": "固定期限/无固定期限/以完成一定工作任务为期限"},
        {"key": "work_content", "name": "工作内容与地点", "description": "岗位、工作地点"},
        {"key": "working_hours", "name": "工作时间", "description": "工时制度（标准/综合/不定时）"},
        {"key": "salary", "name": "劳动报酬", "description": "工资构成、支付周期、不低于当地最低工资标准"},
        {"key": "social_insurance", "name": "社会保险与福利", "description": "五险一金约定"},
        {"key": "probation", "name": "试用期", "description": "试用期期限、工资不得低于转正后 80%"},
        {"key": "non_compete", "name": "竞业限制", "description": "如约定需支付经济补偿（30% 月薪）"},
        {"key": "termination_conditions", "name": "解除/终止条件", "description": "法定解除条件 + 双方约定"},
        {"key": "liability", "name": "违约责任", "description": "违约金、赔偿责任"},
    ],
    "sale": [
        {"key": "parties", "name": "买卖双方信息", "description": "出卖人与买受人完整信息"},
        {"key": "subject", "name": "标的物", "description": "标的物名称、规格、型号"},
        {"key": "quantity", "name": "数量", "description": "标的物数量"},
        {"key": "price", "name": "价款", "description": "单价、总价、币种"},
        {"key": "delivery_method", "name": "交付方式", "description": "交付时间、地点、方式、运输费用"},
        {"key": "transfer_of_risk", "name": "风险转移", "description": "标的物毁损灭失风险转移时点"},
        {"key": "transfer_of_ownership", "name": "所有权转移", "description": "所有权转移时间"},
        {"key": "quality_standard", "name": "质量标准", "description": "质量要求、检验方式"},
        {"key": "warranty", "name": "质量保证期", "description": "质保期及责任"},
        {"key": "breach", "name": "违约责任", "description": "逾期付款/逾期交货的违约金"},
        {"key": "dispute_resolution", "name": "争议解决", "description": "管辖约定"},
    ],
    "lease": [
        {"key": "parties", "name": "租赁双方", "description": "出租人与承租人信息"},
        {"key": "property", "name": "租赁物", "description": "房屋地址、面积、产权证号"},
        {"key": "purpose", "name": "租赁用途", "description": "明确用途（住宅/商业/办公）"},
        {"key": "term", "name": "租赁期限", "description": "起止时间，不超过 20 年"},
        {"key": "rent", "name": "租金", "description": "月租金、支付周期、支付方式"},
        {"key": "deposit", "name": "押金", "description": "押金金额、退还条件"},
        {"key": "maintenance", "name": "维修责任", "description": "出租人/承租人各自承担范围"},
        {"key": "improvements", "name": "装修与改造", "description": "装修/改造的同意与拆除"},
        {"key": "sublease", "name": "转租", "description": "是否允许转租"},
        {"key": "termination", "name": "提前解除", "description": "提前解除条件与违约金"},
        {"key": "force_majeure", "name": "不可抗力", "description": "不可抗力处理"},
    ],
    "service": [
        {"key": "parties", "name": "服务双方", "description": "服务商与客户信息"},
        {"key": "service_content", "name": "服务内容", "description": "服务范围、规格、要求"},
        {"key": "service_standard", "name": "服务标准", "description": "服务质量的明确标准"},
        {"key": "service_fee", "name": "服务费", "description": "费用构成、总额、支付节点"},
        {"key": "delivery", "name": "服务期限与地点", "description": "服务起止时间、地点、方式"},
        {"key": "acceptance", "name": "验收", "description": "验收标准与方法"},
        {"key": "ip", "name": "知识产权", "description": "服务成果的知识产权归属"},
        {"key": "confidentiality", "name": "保密", "description": "保密义务、期限、违约金"},
        {"key": "liability", "name": "违约责任", "description": "违约金、损害赔偿"},
        {"key": "dispute_resolution", "name": "争议解决", "description": "管辖约定"},
    ],
}


# ===== 高风险关键词/模式 =====
HIGH_RISK_PATTERNS = [
    {
        "id": "limitation_liability_escape",
        "name": "免除自身责任条款",
        "pattern": r"(免除|排除|限制).{0,30}(责任|义务|赔偿|违约)",
        "risk_level": "high",
        "law_basis": "民法典 第五百零六条（格式条款无效情形）",
        "suggestion": "建议删除或修改为'依法承担相应责任'，避免被认定为格式条款无效",
    },
    {
        "id": "unilateral_termination",
        "name": "单方解除权不对等",
        "pattern": r"(一方|单方|任意|无需理由).{0,20}解除.{0,20}合同",
        "risk_level": "high",
        "law_basis": "民法典 第五百六十二条",
        "suggestion": "解除权应对等，避免被认定格式条款无效；建议增加法定解除条件",
    },
    {
        "id": "excessive_liquidated_damages",
        "name": "违约金过高",
        "pattern": r"违约金.{0,30}总.{0,5}价.{0,5}款.{0,5}的.{0,10}(30|40|50|[3-9]\d|100)%",
        "risk_level": "high",
        "law_basis": "民法典 第五百八十五条（违约金不得过分高于实际损失）",
        "suggestion": "违约金一般不超过实际损失 30%，约定过高可申请法院调减",
    },
    {
        "id": "ip_unclear",
        "name": "知识产权归属不明",
        "pattern": r"知识产权.{0,20}(归|属于|所有)",
        "risk_level": "medium",
        "law_basis": "民法典 第五百一十一条",
        "suggestion": "建议明确约定成果的知识产权归属（特别是服务/委托开发合同）",
    },
    {
        "id": "jurisdiction_overseas",
        "name": "海外管辖或适用外国法律",
        "pattern": r"(适用|管辖).{0,30}(外国|境外|海外|香港|澳门|台湾).{0,10}(法律|管辖)",
        "risk_level": "medium",
        "law_basis": "民法典 第四百六十七条",
        "suggestion": "海外管辖与外国法律适用会大幅增加诉讼成本，建议改为中国法院管辖",
    },
    {
        "id": "no_dispute_resolution",
        "name": "未约定争议解决",
        "pattern": r"^.{0,500}$",
        "exclude": r"(争议|诉讼|仲裁|管辖|纠纷)",
        "risk_level": "high",
        "law_basis": "民事诉讼法 第二十四条",
        "suggestion": "建议明确约定管辖法院（原告住所地/被告住所地/合同履行地）或仲裁机构",
    },
    {
        "id": "no_force_majeure",
        "name": "无不可抗力条款",
        "exclude": r"不可抗力",
        "risk_level": "medium",
        "law_basis": "民法典 第五百九十条",
        "suggestion": "建议增加不可抗力条款，约定不能履行时的通知义务和证明责任",
    },
    {
        "id": "no_breach_clause",
        "name": "无违约责任条款",
        "exclude": r"违约",
        "risk_level": "high",
        "law_basis": "民法典 第五百七十七条",
        "suggestion": "必须约定违约责任，包括违约金、损害赔偿、继续履行等",
    },
    {
        "id": "blank_amount",
        "name": "金额空白待填",
        "pattern": r"(人民币|大写|￥|¥|\$|USD|EUR).{0,5}(\s|_|—){3,}",
        "risk_level": "high",
        "law_basis": "合同法原则",
        "suggestion": "空白金额待填是高风险，建议填具体数字或约定计算方式",
    },
    {
        "id": "auto_renewal",
        "name": "自动续约条款",
        "pattern": r"自动续约|自动续签|自动续展|自动延期",
        "risk_level": "low",
        "law_basis": "民法典 第五百六十四条",
        "suggestion": "自动续约条款应约定明确续约次数、通知期限和退出机制",
    },
]


class ContractReviewService:
    """合同审查服务"""

    def __init__(self):
        self.llm = llm_service
        self.retrieval = retrieval_service

    async def review(
        self,
        contract_text: str,
        contract_type: str = "general",  # general/labor/sale/lease/service
        user_role: str = "中立",  # 我方/对方/中立
    ) -> Dict[str, Any]:
        """审查合同

        Args:
            contract_text: 合同全文
            contract_type: 合同类型
            user_role: 审查立场

        Returns:
            {
                "contract_type": "...",
                "user_role": "...",
                "risk_level": "low/medium/high",
                "risks": [{name, level, location, description, suggestion, law_basis}],
                "missing_clauses": [...],
                "legal_citations": [...],  # RAG 检索到的相关法条
                "summary": "...",
                "overall_suggestion": "...",
            }
        """
        log.info(f"[合同审查] 类型={contract_type}, 立场={user_role}, 长度={len(contract_text)}")

        # 1. 规则引擎 - 高风险模式匹配
        risk_findings = self._scan_risks(contract_text)

        # 2. 必备条款检查
        missing = self._check_required_clauses(contract_text, contract_type)

        # 3. RAG 检索相关法条
        rag_citations = await self._retrieve_legal_basis(contract_text, contract_type)

        # 4. LLM 整体分析（综合）
        llm_analysis = await self._llm_analyze(contract_text, contract_type, user_role, risk_findings, missing)

        # 5. 综合风险等级
        high_count = sum(1 for r in risk_findings if r["risk_level"] == "high")
        medium_count = sum(1 for r in risk_findings if r["risk_level"] == "medium")
        missing_count = len(missing)
        if high_count >= 2 or missing_count >= 3:
            overall = "high"
        elif high_count >= 1 or medium_count >= 2 or missing_count >= 1:
            overall = "medium"
        else:
            overall = "low"

        return {
            "contract_type": contract_type,
            "user_role": user_role,
            "risk_level": overall,
            "risks": risk_findings,
            "missing_clauses": missing,
            "legal_citations": rag_citations,
            "llm_analysis": llm_analysis,
            "summary": self._build_summary(overall, high_count, medium_count, missing_count),
        }

    def _scan_risks(self, text: str) -> List[Dict[str, Any]]:
        """规则引擎扫描高风险条款"""
        findings = []
        text_len = len(text)

        for pat in HIGH_RISK_PATTERNS:
            risk_level = pat["risk_level"]

            if "pattern" in pat:
                # 正向匹配
                matches = list(re.finditer(pat["pattern"], text, re.MULTILINE | re.IGNORECASE))
                if matches:
                    # 取第一个匹配作为示例
                    m = matches[0]
                    start = max(0, m.start() - 30)
                    end = min(text_len, m.end() + 50)
                    excerpt = text[start:end].strip()
                    findings.append({
                        "name": pat["name"],
                        "level": risk_level,
                        "description": f"匹配到 {len(matches)} 处",
                        "location": f"位置 {m.start()}-{m.end()}",
                        "excerpt": excerpt,
                        "suggestion": pat["suggestion"],
                        "law_basis": pat["law_basis"],
                    })
            elif "exclude" in pat:
                # 排除匹配：整段没有该关键词
                if not re.search(pat["exclude"], text, re.IGNORECASE):
                    findings.append({
                        "name": pat["name"],
                        "level": risk_level,
                        "description": f"合同中未发现相关约定",
                        "location": "全文缺失",
                        "excerpt": "(整段合同无此约定)",
                        "suggestion": pat["suggestion"],
                        "law_basis": pat["law_basis"],
                    })

        return findings

    def _check_required_clauses(self, text: str, contract_type: str) -> List[Dict[str, Any]]:
        """检查必备条款缺失"""
        missing = []
        clauses = CONTRACT_REQUIRED_CLAUSES.get(contract_type, CONTRACT_REQUIRED_CLAUSES["general"])

        # 简单的关键词匹配
        keyword_groups = {
            "parties": [r"甲方", r"乙方", r"买方", r"卖方", r"用人单位", r"劳动者", r"出租人", r"承租人", r"服务方", r"客户"],
            "subject": [r"标的", r"商品", r"货物", r"服务内容", r"工作内容", r"标的物"],
            "quantity_quality": [r"数量", r"质量", r"规格"],
            "price_payment": [r"价格", r"价款", r"费用", r"工资", r"薪酬", r"报酬", r"租金", r"支付"],
            "delivery": [r"交付", r"履行", r"提供", r"期限", r"时间"],
            "breach": [r"违约", r"违约金", r"赔偿"],
            "dispute_resolution": [r"争议", r"诉讼", r"仲裁", r"管辖"],
            "force_majeure": [r"不可抗力"],
            "effective_termination": [r"生效", r"解除", r"终止"],
            "signature_date": [r"签字", r"盖章", r"签订", r"签署", r"签章"],
            "term": [r"期限", r"合同期", r"年", r"月"],
            "work_content": [r"工作内容", r"岗位", r"职责"],
            "working_hours": [r"工作时间", r"工时", r"作息"],
            "salary": [r"工资", r"月薪", r"薪资", r"报酬"],
            "social_insurance": [r"社保", r"保险", r"公积金", r"五险"],
            "probation": [r"试用"],
            "non_compete": [r"竞业限制", r"竞业禁止", r"竞业"],
            "termination_conditions": [r"解除", r"终止"],
            "liability": [r"违约", r"赔偿", r"责任"],
            "property": [r"房屋", r"地址", r"位置", r"面积"],
            "purpose": [r"用途", r"目的"],
            "rent": [r"租金", r"月租"],
            "deposit": [r"押金", r"保证金"],
            "maintenance": [r"维修", r"维护", r"修缮"],
            "sublease": [r"转租"],
            "service_content": [r"服务内容", r"服务范围"],
            "service_standard": [r"服务标准", r"质量", r"要求"],
            "service_fee": [r"服务费", r"费用", r"报酬"],
            "acceptance": [r"验收", r"确认"],
            "ip": [r"知识产权", r"版权", r"专利", r"著作权", r"成果"],
            "confidentiality": [r"保密", r"机密", r"商业秘密"],
        }

        for c in clauses:
            keywords = keyword_groups.get(c["key"], [])
            if not keywords:
                continue
            found = any(re.search(p, text, re.IGNORECASE) for p in keywords)
            if not found:
                missing.append({
                    "name": c["name"],
                    "description": c["description"],
                    "suggestion": f"建议增加 {c['name']}：{c['description']}",
                })

        return missing

    async def _retrieve_legal_basis(self, text: str, contract_type: str) -> List[Dict]:
        """RAG 检索相关法条作为依据"""
        # 截取合同前 500 字 + 合同类型作为 query
        query = f"{contract_type} 合同 {text[:500]}"
        try:
            results = await self.retrieval.search(query, top_k=5)
            return [
                {
                    "law_name": r.law_name,
                    "article_no": r.article_no,
                    "article_text": r.text[:200],
                    "source_url": (r.metadata or {}).get("source_url", ""),
                    "score": r.score,
                }
                for r in results
            ]
        except Exception as e:
            log.warning(f"RAG 检索失败: {e}")
            return []

    async def _llm_analyze(
        self,
        contract_text: str,
        contract_type: str,
        user_role: str,
        risks: List[Dict],
        missing: List[Dict],
    ) -> Dict[str, Any]:
        """LLM 综合分析"""
        system = """你是【律瞳·合同审查 Agent】。你的任务是基于用户提供的合同全文和已识别的风险点，给出综合法律分析。

# 严格规则
1. 只基于合同文本和你已识别的风险点，不臆造
2. 重点关注对审查立场（我方/对方/中立）不利的条款
3. 给出可操作的具体修改建议
4. 输出 JSON 格式
"""

        risk_summary = "\n".join([f"- [{r['level']}] {r['name']}: {r['description']}" for r in risks[:10]])
        missing_summary = "\n".join([f"- {m['name']}: {m['description']}" for m in missing[:5]])

        user = f"""# 合同类型
{contract_type}

# 审查立场
{user_role}

# 已识别的风险点
{risk_summary if risk_summary else "（无）"}

# 缺失的必备条款
{missing_summary if missing_summary else "（无）"}

# 合同全文
{contract_text[:3000]}

# 任务
请基于上述信息，从【{user_role}】立场给出：
1. 整体评价（不超过 200 字）
2. 重点关注的 3 个条款（按风险从高到低）
3. 建议优先修改的 3 项（具体到条款）
4. 潜在风险提示（不超过 3 个）

# 输出 JSON Schema
{{
  "overall_assessment": "整体评价",
  "key_clauses": [
    {{"clause": "第X条 关于...的约定", "issue": "问题", "impact": "对我方的影响"}}
  ],
  "priority_modifications": [
    {{"clause": "第X条", "current": "当前内容（简要）", "suggested": "建议修改为..."}}
  ],
  "potential_risks": ["风险1", "风险2"]
}}
"""

        try:
            text = await self.llm.chat(
                system=system,
                user=user,
                temperature=0.2,
                max_tokens=2500,
            )
            # 解析 JSON
            from app.services.agents import _safe_parse_json
            return _safe_parse_json(text) or {}
        except Exception as e:
            log.exception(f"LLM 合同分析失败: {e}")
            return {}

    def _build_summary(self, overall: str, high: int, medium: int, missing: int) -> str:
        """生成总结"""
        parts = []
        if overall == "high":
            parts.append(f"⚠️ 高风险合同")
        elif overall == "medium":
            parts.append(f"⚡ 中等风险")
        else:
            parts.append(f"✅ 低风险")
        parts.append(f"发现 {high} 个高风险 / {medium} 个中等风险条款")
        if missing:
            parts.append(f"缺失 {missing} 个必备条款")
        return "，".join(parts)


# 全局实例
contract_reviewer = ContractReviewService()
