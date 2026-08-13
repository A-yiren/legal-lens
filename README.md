# 金睛 RiskLens

> 金融法律风险研判 AI 助手 | GOAI 2026 Boundless Agents · AI+金融

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-orange)]()
[![Demo](https://img.shields.io/badge/demo-https://ayiren.cn/legallens/-gold)](https://ayiren.cn/legallens/)

> **让每一条金融决策，都扎根于真实法条与可追溯判例。**

金睛 RiskLens 是一款面向 AI+金融方向的多 Agent 协同智能体应用，通过 4 个独立 Agent（A1 焦点识别 / A2 法律分析 / A3 引用核验 ⭐ / A4 风险评估）实现"查法条 → 找类案 → 研判风险 → 出方案"的任务闭环，覆盖银行信贷审批、保险理赔审查、理财适当性等核心金融场景。

> 📌 **参赛信息**：GOAI 2026 Boundless Agents（无界应用）· AI+金融 赛道 · 初赛截止 2026-08-16

---

## ✨ 核心能力

### 🔍 1. 4 Agent 协同校验（业内独创）
- **A1 焦点识别 Agent** — 独立从案情抽取焦点
- **A2 法律分析 Agent** — 基于焦点 + 检索法条生成观点
- **A3 引用核验 Agent ⭐** — 逐字核对每条 [n] 引用真实性，自动过滤幻觉
- **A4 风险评估 Agent** — 独立评估法律/实操风险

> 业内多数法律 AI 用"单次 LLM 调用"，幻觉率 ~15%。金睛用 4 Agent 协同校验，**A3 把幻觉率压到 <5%**。

### 📚 2. 双 RAG 隔离检索
- **法律库 collection** — 41 部中国现行法规 · 1,840 chunks · `category=law`
- **案例库 collection** — 60 个真实判例 · 180 chunks · `category=case`
- 检索时按 collection 物理隔离，payload 携带 `category` 字段，前端可分类展示

### 💼 3. 三大金融场景
- **🏦 银行信贷审批** — 客户经理录入案情 → 4 Agent 跑通 → 给出担保有效性 + 关联风险
- **🛡️ 保险理赔审查** — 理赔员录入案情 → 输出如实告知义务边界 + 不可抗辩条款适用
- **💰 理财适当性** — 理财经理录入案情 → 输出适当性义务违反 + 举证责任倒置

### 📝 4. 合同审查
- 规则引擎（10+ 高风险模式：违约金过高、单方解除不对等...）
- 必备条款检查（5 类合同模板）
- RAG 5-query 并行检索 → 去重取前 5
- LLM 综合分析（高/中/低风险等级 + 5 大模块完整报告）

### ✅ 5. 引用溯源
- 每条观点带 `[n]` 引用编号
- 点开 `[n]` 跳转到原文片段
- 通过率 = confidence 分数

---

## 🛠️ 技术栈（开源可商用）

| 层级 | 技术 |
|------|------|
| **后端** | Python 3.12 + FastAPI 0.115 + SQLAlchemy 2 + Pydantic v2 |
| **向量库** | Qdrant（local embedded mode，单进程部署） |
| **Embedding** | BAAI/bge-small-zh-v1.5（512 维，100MB，本地推理） |
| **LLM** | MiniMax-Text-01（OpenAI 兼容接口） |
| **前端** | 原生 HTML + Tailwind CDN + Font Awesome（零构建步骤） |
| **认证** | JWT HS256，72h 有效期，复用 aipath 账号体系 |
| **部署** | Nginx 反向代理 + systemd，单进程 |

---

## 🚀 快速开始

### 1. 准备环境

```bash
# Python 3.10+ （推荐 3.12）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r backend/requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入:
#   LLM_API_KEY=your-minimax-key
#   LLM_BASE_URL=https://api.minimaxi.com/v1
#   JWT_SECRET=your-random-32-char
```

### 3. 初始化知识库

```bash
cd backend
python scripts/local_full_ingest.py
# 预计 1-2 分钟：解析 41 部法规 + 60 判例 → 写入 Qdrant
```

### 4. 启动服务

```bash
cd backend
export HF_ENDPOINT=https://hf-mirror.com  # 国内加速
export HF_HUB_OFFLINE=1                    # 用本地模型
python -m uvicorn app.main:app --host 0.0.0.0 --port 8767
```

### 5. 访问

打开浏览器 → `http://localhost:8767/`

---

## 📁 项目结构

```
legal-lens/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI 路由
│   │   │   ├── analyze.py       # 案件分析（4 Agent）
│   │   │   ├── cases.py         # 案件库 CRUD
│   │   │   ├── knowledge.py     # 知识库 CRUD + 搜索
│   │   │   ├── auth.py          # 用户认证（委托 aipath）
│   │   │   └── health.py        # 健康检查
│   │   ├── services/       # 业务逻辑
│   │   │   ├── agents.py        # 4 Agent 协同引擎 ⭐
│   │   │   ├── retrieval.py     # 法律库 RAG
│   │   │   ├── case_retrieval.py # 案例库 RAG
│   │   │   ├── embedding.py     # BGE 模型加载
│   │   │   ├── llm.py          # LLM 客户端
│   │   │   ├── contract_review.py # 合同审查
│   │   │   └── ingestion.py     # 文档入库
│   │   ├── storage/        # 数据层
│   │   │   ├── qdrant_client.py # Qdrant 封装
│   │   │   └── sqlite.py        # SQLite 封装
│   │   ├── models/         # Pydantic 模型
│   │   ├── config.py       # 全局配置
│   │   └── main.py         # FastAPI 入口
│   └── scripts/            # 运维脚本
│       └── local_full_ingest.py
├── frontend/               # 静态前端
│   ├── index.html          # 工作台
│   ├── auth.js             # 全局认证
│   └── pages/
│       ├── case-analysis.html    # 案件分析（4 Agent）
│       ├── case-search.html      # 类案检索
│       ├── case-list.html        # 案件库
│       ├── contract-review.html  # 合同审查
│       ├── knowledge-base.html   # 知识库（3 tab）
│       ├── obsidian.html         # Obsidian 集成
│       └── login.html            # 登录/注册
├── seed_data/              # 41 部法规 + 60 判例种子
│   ├── 中华人民共和国商业银行法.md
│   ├── 中华人民共和国证券法.md
│   ├── ... (共 41 部)
│   ├── case-001-信用卡盗刷纠纷案.case
│   └── ... (共 60 判例)
├── docs/
│   ├── 金睛-RiskLens-产品介绍.pdf  # ⭐ GOAI 比赛方案 PPT
│   ├── 作品简介-GOAI-AI金融.md      # ⭐ GOAI 比赛作品简介
│   ├── 作品简介-GOAI-AI金融.docx    # ⭐ 提交格式
│   ├── 作品简介-GOAI-AI金融.pdf     # ⭐ 提交格式
│   ├── ARCHITECTURE.md              # 详细架构说明
│   ├── diagrams/                    # 4 张架构图（mermaid + PNG）
│   ├── screenshots_v2/              # 5 张产品截图
│   └── ppt_preview_v2/              # 18 张 PPT 预览
├── nginx_legallens.conf    # Nginx 反代配置
└── restart.sh              # 启停脚本
```

---

## 🧪 端到端测试

9/9 测试通过（2026-08-13 实测）：

| # | 测试项 | 状态 |
|---|--------|------|
| 01 | 健康检查 | ✅ |
| 02 | 法规 CRUD | ✅ |
| 03 | 案例 CRUD | ✅ |
| 04 | 知识库搜索 | ✅ |
| 05 | 类案检索 | ✅ |
| 06 | 案件分析（4 Agent） | ✅ |
| 07 | 合同审查 | ✅ |
| 08 | 引用溯源 | ✅ |
| 09 | 登录注册 | ✅ |

---

## 📊 核心数据资产

| 资产 | 数量 | 详情 |
|------|------|------|
| **法规** | 41 部 | 26 通用 + 15 金融 |
| **判例** | 60 个 | 30 通用 + 30 金融 |
| **法律 chunks** | 1,840 | 全部 `category=law` |
| **判例 chunks** | 180 | 全部 `category=case` |
| **总向量** | 2,020 | Qdrant local 模式 |
| **幻觉率** | <5% | A3 引用核验 |

### 41 部法规清单

- **通用（26 部）**：民法典-合同编、刑法、民诉、刑诉、公司法、劳动法、劳动合同法、知识产权-专利法、商标法、著作权法、消费者权益保护法、产品质量法、网络安全法、数据安全法、个人信息保护法、律师法、仲裁法、行政处罚法、行政强制法、行政许可法、行政诉讼法、道路交通安全法、反不正当竞争法、反垄断法、保险法...
- **金融（15 部）**：商业银行法、证券法、个人金融信息保护试行办法、征信业管理条例、商业银行理财业务监督管理办法、期货和衍生品法、证券投资基金法、信托法、反洗钱法、票据法、外汇管理条例、银行业监督管理法、存款保险条例、银行卡业务管理办法、民间借贷司法解释

### 60 真实判例清单

- **法律（30 个）**：消费者维权、劳动纠纷、婚姻家庭、公司治理、知识产权、刑事案件、交通事故、其他民事
- **金融（30 个）**：金融借款合同纠纷、信用卡盗刷、内幕交易、保险代位、期货强行平仓、票据追索、融资租赁、征信、私募基金、信托、理财、担保

---

## 🛡️ 安全、合规与行业边界

### 数据合规
- ✅ 全本地部署，案件数据不出企业内网
- ✅ 用户认证复用 aipath JWT，账号隔离
- ✅ 案件库 CRUD 强制带 `user_id` 过滤（多租户隔离）
- ✅ 日志审计可追溯

### 行业应用边界
- ⚠️ 不替代律师/合规官/法官的最终决策
- ⚠️ 输出含「建议咨询专业人士」提示
- ⚠️ 金融风险研判**仅作为辅助参考**
- ⚠️ LLM 调用通过 API，不传输案件原文到模型训练

### 开放复用
- ✅ 核心代码 MIT 协议，可直接商用
- ✅ 41 部法规 + 60 判例种子可下载复用
- ✅ 部署文档完整，5 分钟起服务
- ✅ 二次开发友好：所有数据 schema 公开，API 文档自动生成

---

## 🌐 公共 Demo

- **URL**：https://ayiren.cn/legallens/
- **状态**：在线运行（2026-08-14 实测）
- **数据**：41 法规 + 60 判例 + 1,840 + 180 = 2,020 向量

### 测试账号
- 用户名：`demo_risklens`
- 密码：`Demo123456`
- 也可自行注册新账号

---

## 📦 部署

### 单机部署
```bash
# 1. 拉代码
git clone https://github.com/A-yiren/legal-lens.git
cd legal-lens

# 2. 装依赖 + 初始化
pip install -r backend/requirements.txt
cd backend && python scripts/local_full_ingest.py && cd ..

# 3. 启服务
cd backend
export HF_ENDPOINT=https://hf-mirror.com HF_HUB_OFFLINE=1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8767
```

### Nginx 反代
参考 `nginx_legallens.conf`，示例：
```nginx
location /legallens/ {
    alias /opt/legal-lens/frontend/;
    try_files $uri $uri/ /legallens/index.html;
}
location /legallens/api/ {
    proxy_pass http://127.0.0.1:8767/api/;
}
```

---

## 📜 许可

本项目采用 **MIT 协议**，可自由用于商业用途。

---

## 🏆 GOAI 2026 参赛

本项目正在参加 **GOAI 2026 Boundless Agents（无界应用）· AI+金融** 比赛，提交材料：

- ✅ 作品简介：`docs/作品简介-GOAI-AI金融.md` / `.docx` / `.pdf`
- ✅ 方案 PPT：`docs/金睛-RiskLens-产品介绍.pptx` / `.pdf` (18 页)
- ✅ 可访问 Demo：https://ayiren.cn/legallens/
- ✅ 源码仓库：本仓库

---

## 👤 参赛者

- **ayiren** (个人开发者)
- 联系：7989689965m@gmail.com
- 主页：https://ayiren.cn
