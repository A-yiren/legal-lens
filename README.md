# 律瞳 LegalLens

> 律师专属 AI 案件分析平台 | Multi-Agent 校验 RAG + 引用溯源 + 类案检索 + 合同审查

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-orange)]()

## ✨ 核心特性

### 🤖 4 Agent 协同校验（不是单一 LLM）
- **A1 焦点识别 Agent** - 独立从案情抽焦点
- **A2 法律分析 Agent** - 基于焦点 + 检索法条生成观点
- **A3 引用校验 Agent ⭐** - 逐字核对每条引用 [n] 是否支持观点，自动剔除幻觉引用
- **A4 风险评估 Agent** - 独立评估诉讼风险/实操风险

### 📚 类案检索
- 内置 30 个真实判例（覆盖合同/婚姻/劳动/交通/刑事/知产/公司治理等 8 大领域）
- 支持按案由、法院级别过滤
- 每个案件展示：案号 / 法院 / 案由 / 引用法条 / 胜负 / 全文摘要

### 📝 合同审查
- **规则引擎**：10+ 高风险条款模式（违约金过高 / 单方解除不对等 / 知识产权不明 / 管辖约定等）
- **必备条款检查**：通用 / 劳动 / 买卖 / 租赁 / 服务合同分别有不同检查模板
- **RAG 检索**：自动匹配相关法条作为依据
- **LLM 综合分析**：基于审查立场（我方/对方/中立）给出建议

### 📌 引用溯源
- 每条引用都带：法名 / 条号 / 原文 / 官方源 URL / 发布者 / 版本时效
- "✓ 官方源" 链接一键跳到外部原文
- "📖 原文" 链接跳到知识库预览

### 🔧 技术栈（开源可商用）
- **后端**：FastAPI + Python 3.10+
- **向量数据库**：Qdrant（本地 embedded 模式）
- **Embedding**：BAAI/bge-small-zh-v1.5（100MB，中文法律友好）
- **LLM**：MiniMax-Text-01（可替换 OpenAI/Claude/通义）
- **前端**：Tailwind CSS + Vanilla JS（无框架依赖）
- **检索**：混合检索（dense + sparse） + Reranker

## 🚀 快速开始

### 1. 准备环境
```bash
# Python 3.10+
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install fastapi uvicorn qdrant-client sentence-transformers requests pydantic python-dotenv loguru
```

### 2. 启动后端
```bash
cd backend
HF_HUB_OFFLINE=1 HF_ENDPOINT=https://hf-mirror.com \
python -m uvicorn app.main:app --host 0.0.0.0 --port 8767
```

### 3. 入库种子数据
```bash
# 入库 26 部法律
python3 scripts/seed_data.py

# 入库 30 个真实判例
python3 scripts/seed_cases.py
```

### 4. 访问
- API: http://localhost:8767/docs
- 前端：把 `frontend/` 目录用 nginx 代理到 `/legallens/`

## 📁 项目结构

```
legal-lens/
├── backend/
│   ├── app/
│   │   ├── api/                  # API 路由
│   │   │   ├── analyze.py        # 案件分析（4 Agent）
│   │   │   ├── cases.py          # 类案 + 合同审查
│   │   │   ├── knowledge.py      # 知识库
│   │   │   ├── health.py
│   │   │   └── obsidian.py
│   │   ├── services/
│   │   │   ├── agents.py         # 4 Agent 编排 ⭐
│   │   │   ├── case_retrieval.py # 类案检索
│   │   │   ├── contract_review.py# 合同审查
│   │   │   ├── generation.py     # 案件分析（旧版）
│   │   │   ├── retrieval.py      # 混合检索
│   │   │   ├── embedding.py      # 向量化
│   │   │   ├── llm.py            # LLM 抽象层
│   │   │   └── reranker.py
│   │   ├── models/               # Pydantic 数据模型
│   │   ├── storage/              # Qdrant + SQLite
│   │   ├── parsers/              # 文档解析
│   │   ├── chunkers/             # 切分策略
│   │   ├── config.py
│   │   └── main.py
│   ├── scripts/
│   │   ├── seed_data.py          # 法律种子入库
│   │   ├── seed_cases.py         # 案件种子入库
│   │   ├── scrape_official.py    # 官方源爬取
│   │   └── reset_db.py
│   └── data/
├── frontend/
│   ├── index.html                # 工作台
│   ├── pages/
│   │   ├── case-analysis.html    # 案件分析（4 Agent）
│   │   ├── case-list.html        # 案件库
│   │   ├── knowledge-base.html   # 知识库
│   │   └── obsidian.html
│   └── assets/
├── seed_data/                    # 26 部法律 md
├── seed_data_cases/              # 30 个判例 jsonl
├── verify-screenshots/           # 验证截图
├── test_cases.md                 # 8 个测试案情
└── README.md
```

## 🧪 测试

打开 `test_cases.md` 看 8 个跨领域测试案情。复制到案件分析页即可。

## 📊 路线图

- [x] Phase 1: 基础 RAG + 26 部法律
- [x] Phase 2: 4 Agent 校验 + 官方源溯源
- [x] Phase 3: 类案检索 + 合同审查
- [ ] Phase 4: 算法备案（《生成式人工智能服务管理暂行办法》）
- [ ] Phase 5: 接入 CAIL 大数据集（10万+ 真实判例）
- [ ] Phase 6: 文书生成（起诉状 / 答辩状 / 合同模板）

## 📄 License

MIT
