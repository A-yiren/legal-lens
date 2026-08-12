# 律瞳 LegalLens — 技术架构设计文档

> **核心理念：让 AI 推理扎根于真实法律条文，让每一次输出都可溯源**

---

## 一、目标与边界

### 1.1 MVP 目标

做出一个**能真跑的法律 AI 终端 + 知识库**系统：

1. **真实文档入库**：用户上传 PDF/Word/Markdown/TXT，系统自动解析 → 切分 → Embedding → 入库
2. **Obsidian vault 集成**：用户配置本地 Obsidian 笔记库路径，系统自动同步
3. **真 RAG 检索**：基于案情描述，混合检索（向量 + 关键词 + 重排序）找到最相关法条
4. **LLM 生成 + 引用**：用 MiniMax/智谱生成结构化分析，每个观点附带法条引用
5. **引用溯源**：用户点击 AI 输出中的引用气泡，秒级定位原文

### 1.2 非目标（MVP 不做）

- 多用户权限/团队协作（P1）
- 文书自动生成（P1）
- 多轮对话记忆（P1）
- 移动端（P2）

---

## 二、技术选型（基于 2025-2026 调研）

| 层 | 选型 | 理由 |
|----|------|------|
| **Embedding** | BGE-M3（智源）| 中文 SOTA，100+ 语言，8192 token，三合一（Dense+Sparse+Multi-vector），免费开源 |
| **Rerank** | BGE-Reranker-v2-M3 | 同源，Cross-Encoder 精度高，对法律引用溯源关键 |
| **向量数据库** | Qdrant 1.9+ | Rust 性能优异，原生支持混合搜索（dense+sparse），Docker 部署简单 |
| **LLM** | MiniMax abab6.5s（主）| 国内稳定，已开通；备选 GLM-4 / 通义千问 |
| **后端框架** | FastAPI | 异步、高性能、自动 OpenAPI 文档 |
| **业务数据库** | SQLite | 用户偏好，单文件，零运维 |
| **文档解析** | PyMuPDF + python-docx + markdown-it-py | 全格式覆盖 |
| **Obsidian 监听** | watchdog | 跨平台文件监控 |
| **前端** | HTML + Tailwind CDN + Vanilla JS | 复用之前的工作台 UI，零构建 |
| **部署** | Docker Compose | 一键起 Qdrant + Backend |
| **进程管理** | uvicorn（开发） / gunicorn（生产） | 标准 ASGI |

---

## 三、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (HTML/Tailwind/JS)                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ 工作台   │ │ 案件分析 │ │ 知识库   │ │ 法条详情 │         │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘         │
└───────┼─────────────┼────────────┼─────────────┼─────────────┘
        │             │            │             │
        │  HTTP/REST  │            │             │
        ▼             ▼            ▼             ▼
┌─────────────────────────────────────────────────────────────┐
│                FastAPI Backend (Python)                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐             │
│  │ /cases      │ │ /analyze    │ │ /knowledge  │             │
│  │ CRUD        │ │ RAG 引擎    │ │ 文档管理    │             │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘             │
│         │               │               │                     │
│  ┌──────┴───────────────┴───────────────┴──────┐             │
│  │            RAG 引擎核心                      │             │
│  │  Query 改写 → 混合检索 → 重排序 → 上下文组装 │             │
│  └──────┬───────────────┬──────────────────────┘             │
│         │               │                                     │
│  ┌──────▼──────┐  ┌─────▼──────┐  ┌──────────────┐          │
│  │  Ingestion  │  │ Retrieval  │  │  Generation  │          │
│  │  Pipeline   │  │  Service   │  │  Service     │          │
│  └──────┬──────┘  └─────┬──────┘  └──────┬───────┘          │
│         │               │               │                     │
│  ┌──────▼───────────────▼───────────────▼────────┐           │
│  │           Storage & Indexing                  │           │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────┐    │           │
│  │  │ SQLite   │ │ Qdrant   │ │ FileSystem │    │           │
│  │  │ 业务数据 │ │ 向量索引 │ │ 原始文档   │    │           │
│  │  └──────────┘ └──────────┘ └────────────┘    │           │
│  └───────────────────────────────────────────────┘           │
│                                                                │
│  ┌───────────────────────────────────────────────┐           │
│  │  Obsidian Watcher (watchdog)                  │           │
│  │  监听 vault 目录 → 解析 .md → 入库            │           │
│  └───────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
        │                                       │
        │  HTTP/Embeddings                      │  HTTPS
        ▼                                       ▼
┌──────────────────┐                ┌──────────────────────┐
│  BGE-M3 Service  │                │  MiniMax API          │
│  (FlagEmbedding)  │                │  (LLM Generation)     │
│  本地推理 7860    │                │  api.minimaxi.com     │
└──────────────────┘                └──────────────────────┘
```

---

## 四、模块详细设计

### 4.1 Ingestion Pipeline（文档入库）

**流程**：

```
原始文件（PDF/Word/MD/TXT）
    ↓ [DocumentParser]
结构化文本 + 元数据（标题/作者/章节）
    ↓ [LegalStructureParser] ← 法律领域特化
法条结构（条/款/项）+ 元数据（效力级别/实施日期）
    ↓ [Chunker]
Chunk 列表（每条保留父级上下文）
    ↓ [Embedding]
BGE-M3 Dense + Sparse 向量
    ↓ [Indexer]
Qdrant 入库 + SQLite 业务记录
```

**法律领域结构化切分规则**：

```python
# 民法典类法律的典型结构
# 第X条 → 款（自然段） → 项（(一)(二)）→ 目
# 解析后产出：
{
  "article_no": "第五百七十七条",  # 条号
  "article_text": "...",  # 条全文
  "paragraphs": [
    {"no": 1, "text": "..."},
    {"no": 2, "text": "..."}
  ],
  "items": [
    {"marker": "（一）", "text": "..."}
  ],
  "metadata": {
    "law_name": "中华人民共和国民法典",
    "book": "合同编",
    "chapter": "违约责任",
    "effective_date": "2021-01-01",
    "status": "现行有效"
  }
}
```

### 4.2 Retrieval Service（检索）

**三阶段混合检索**：

```
用户查询
    ↓ [Query Rewriter] ← LLM 改写
优化查询（去口语化、补充法律术语）
    ↓ [并行三路召回]
┌─ Dense（向量相似度，BGE-M3）
├─ Sparse（BM25 风格，BGE-M3 Sparse）
└─ 元数据过滤（按 law_name / status / book）
    ↓ [RRF 融合]
Top-20 候选
    ↓ [BGE-Reranker-v2]
重排序
    ↓ [Context Assembler]
Top-5 上下文 + 引用 ID
```

### 4.3 Generation Service（生成）

**Prompt 模板（引用溯源关键）**：

```python
SYSTEM = """你是【律瞳】，一位专业的律师助理。基于检索到的法律条文分析案情。

严格规则：
1. 只能基于【法律条文】中的内容回答，不可编造
2. 每条法律观点后必须标注引用编号 [1][2][3]...
3. 如果检索到的条文不足以回答，明确说明"现有知识库暂无法支持该分析"
4. 不得给出最终法律意见，只提供分析参考
"""

USER_TEMPLATE = """案情描述：
{case_description}

法律条文：
{context_with_citations}

要求：
1. 识别案件焦点
2. 基于上述条文分析，引用条文编号
3. 标注风险点
4. 给出下一步建议
"""
```

**输出格式**（结构化 JSON）：

```json
{
  "case_focus": [...],
  "legal_analysis": [
    {
      "text": "...",
      "citations": [1, 2]
    }
  ],
  "risks": [...],
  "next_steps": [...]
}
```

### 4.4 Obsidian Watcher

**流程**：

```
Obsidian vault 目录
    ↓ [watchdog 监听]
文件变更事件（创建/修改/删除）
    ↓ [.md 解析]
{
  "frontmatter": {...},  # YAML 元数据
  "content": "...",  # 正文
  "links": [["目标笔记", "显示文本"]],  # [[双向链接]]
  "tags": [...]  # #标签
}
    ↓ [与向量库关联]
作为一类特殊文档入库（source_type=obsidian）
```

---

## 五、目录结构

```
legal-lens/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI 入口
│   │   ├── config.py                  # 配置
│   │   ├── api/
│   │   │   ├── cases.py               # 案件 API
│   │   │   ├── knowledge.py           # 知识库 API
│   │   │   ├── analyze.py             # 案件分析 API
│   │   │   ├── obsidian.py            # Obsidian 集成 API
│   │   │   └── health.py              # 健康检查
│   │   ├── services/
│   │   │   ├── ingestion.py           # 文档入库管道
│   │   │   ├── retrieval.py           # 检索服务
│   │   │   ├── generation.py          # 生成服务
│   │   │   ├── embedding.py           # Embedding 客户端
│   │   │   ├── reranker.py            # Rerank 客户端
│   │   │   └── llm.py                 # LLM 客户端
│   │   ├── parsers/
│   │   │   ├── base.py                # 解析器基类
│   │   │   ├── pdf_parser.py          # PDF
│   │   │   ├── docx_parser.py         # Word
│   │   │   ├── md_parser.py           # Markdown
│   │   │   ├── txt_parser.py          # TXT
│   │   │   └── legal_structure.py     # 法律结构化
│   │   ├── chunkers/
│   │   │   ├── base.py
│   │   │   ├── legal_chunker.py       # 法律条文章节切分
│   │   │   └── semantic_chunker.py    # 通用语义切分
│   │   ├── storage/
│   │   │   ├── sqlite.py              # SQLite ORM
│   │   │   ├── qdrant_client.py       # Qdrant 客户端
│   │   │   └── file_store.py          # 文件存储
│   │   ├── watchers/
│   │   │   └── obsidian_watcher.py    # Obsidian 监听
│   │   ├── models/
│   │   │   ├── document.py
│   │   │   ├── case.py
│   │   │   ├── chunk.py
│   │   │   └── analysis.py
│   │   └── utils/
│   │       ├── logging.py
│   │       └── text.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html
│   └── pages/
│       ├── case-analysis.html
│       ├── case-list.html
│       ├── knowledge-base.html
│       ├── law-detail.html
│       └── report.html
├── storage/                            # 运行时数据
│   ├── uploads/                        # 用户上传
│   ├── sqlite/                         # 业务数据
│   └── qdrant/                         # 向量数据
├── obsidian_vault/                     # 测试用 Obsidian
│   ├── 民法典/
│   │   ├── 合同编.md
│   │   └── 侵权责任编.md
│   └── 案件模板.md
├── scripts/
│   ├── start.sh                        # 一键启动
│   ├── seed_data.py                    # 种子数据
│   └── ingest_law.py                   # 法律入库脚本
├── docker-compose.yml
├── README.md
└── .env.example
```

---

## 六、API 契约

### 6.1 知识库管理

```http
POST /api/knowledge/upload
Content-Type: multipart/form-data
Body: file=@xxx.pdf, source=law|case|obsidian
→ { doc_id, chunks_count, status }

GET /api/knowledge/documents
→ [{ id, name, source, chunks, uploaded_at, status }]

DELETE /api/knowledge/documents/{id}
→ { status: "deleted" }

POST /api/knowledge/search
Body: { query, top_k, filters? }
→ [{ content, metadata, score }]
```

### 6.2 案件分析

```http
POST /api/analyze
Body: {
  case_id: "case-001",
  case_description: "...",
  stream: true
}
→ Server-Sent Events 流式输出
  data: {"type": "token", "content": "..."}
  data: {"type": "citation", "id": 1, "law": "民法典", "article": "第577条"}
  data: {"type": "done", "analysis_id": "..."}

GET /api/analyze/{analysis_id}
→ 完整分析结果（含所有引用）
```

### 6.3 Obsidian 集成

```http
POST /api/obsidian/configure
Body: { vault_path: "C:/Users/.../Vault" }
→ { status: "watching", files_count: 142 }

GET /api/obsidian/status
→ { status, files_count, last_sync, errors? }

POST /api/obsidian/sync
→ 手动触发全量同步
```

---

## 七、性能指标（验收标准）

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 文档解析速度 | 1MB PDF < 3s | 上传时打点 |
| Embedding 速度 | 100 chunk/s | 批量入库时打点 |
| 检索 P99 延迟 | < 500ms | API 计时 |
| 端到端分析时间 | < 8s（首字） | 包含 LLM 首字延迟 |
| 引用准确率 | ≥ 95% | 人工抽检 50 个用例 |

---

## 八、安全与合规

- **数据隔离**：所有数据本地存储（SQLite + 本地向量库 + 本地文件）
- **传输加密**：生产环境配 HTTPS
- **LLM 调用**：MiniMax 国内版 API，数据不出境
- **审计日志**：所有 API 调用留痕（律师行业硬性要求）
- **隐私保护**：导出报告时支持敏感信息脱敏

---

## 九、后续迭代路线

| 版本 | 周期 | 内容 |
|------|------|------|
| MVP | 2 周 | 文档入库 + 检索 + 分析 + 引用 |
| V1.0 | +4 周 | 多轮对话 + 团队协作 + 文书草稿 |
| V1.5 | +4 周 | 案件模板 + 案由分类 + 类案推送 |
| V2.0 | +8 周 | 庭审模拟 + 证据链梳理 |
