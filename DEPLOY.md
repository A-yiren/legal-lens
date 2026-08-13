# 金睛 RiskLens — 部署与运维指南

> 本文面向运维/开发人员，介绍金睛 RiskLens 的部署、配置、运维细节。

---

## 一、环境要求

| 组件 | 最低 | 推荐 |
|------|------|------|
| Python | 3.10 | 3.12 |
| 内存 | 1.5 GB | 4 GB |
| 磁盘 | 2 GB | 5 GB（含模型） |
| 操作系统 | Linux / macOS | Ubuntu 22.04+ |
| 网络 | 阿里云/腾讯云 ECS 公网 IP | 国内服务器（LLM 调用稳定） |

> ⚠️ **不要在同一台机器上同时跑 uvicorn + ingestion + embedding 进程**，会 OOM。
> 推荐先停 uvicorn → 跑 ingestion → 启 uvicorn。

---

## 二、部署步骤

### 1. 拉代码

```bash
cd /opt
git clone https://github.com/A-yiren/legal-lens.git
cd legal-lens
```

### 2. 创建虚拟环境 + 装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install --break-system-packages -r backend/requirements.txt
```

> 阿里云 Ubuntu 24 默认 Python 3.12，需要 `--break-system-packages`（PEP 668）。

### 3. 配置环境变量

```bash
cp .env.example .env
nano .env
```

最小配置（必填）：
```bash
APP_NAME=金睛 RiskLens
APP_VERSION=0.2.0

# LLM (MiniMax 国内版)
LLM_PROVIDER=minimax
LLM_API_KEY=eyJhbGciOiJ...
LLM_BASE_URL=https://api.minimaxi.com/v1
LLM_MODEL=MiniMax-Text-01

# Embedding (本地 bge-small-zh-v1.5)
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
EMBEDDING_DIM=512

# JWT
JWT_SECRET=your-random-32-char-string-xxxxx
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=72

# Qdrant (local 模式)
QDRANT_MODE=local
QDRANT_PATH=./storage/qdrant

# Storage
STORAGE_ROOT=./storage
UPLOAD_DIR=./storage/uploads
LOG_DIR=./storage/logs
```

### 4. 下载 Embedding 模型（仅首次）

```bash
# 国内镜像
export HF_ENDPOINT=https://hf-mirror.com

# 下载 bge-small-zh-v1.5
python download_model.py
# 100MB，5-10 分钟
```

模型默认下载到 `~/.cache/huggingface/`，建议软链到项目内：
```bash
ln -s ~/.cache/huggingface/ ./models_cache
```

### 5. 初始化知识库

```bash
cd backend
python scripts/local_full_ingest.py
```

输出：
```
[law] 中华人民共和国商业银行法.md -> 45 chunks
[law] 中华人民共和国证券法.md -> 68 chunks
...
[case] case-001-信用卡盗刷纠纷案.case -> 3 chunks
[case] case-101-金融借款合同纠纷案.case -> 3 chunks
...
✅ Done: 41 laws + 60 cases = 2020 chunks in 75.2s
```

### 6. 启动服务

```bash
# 前台（调试用）
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8767

# 后台（生产用）
cd backend
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_OFFLINE=1
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8767 \
    > /opt/legal-lens/storage/logs/uvicorn.log 2>&1 &
```

### 7. 验证

```bash
curl http://127.0.0.1:8767/api/health
# {"app":"金睛 RiskLens","version":"0.2.0","vector_count":2020,"doc_count":101}
```

---

## 三、Nginx 反向代理（公网部署）

### 1. 配置文件

`/etc/nginx/sites-available/legallens`:

```nginx
server {
    listen 80;
    server_name ayiren.cn;

    # 金睛 RiskLens
    location /legallens/ {
        alias /opt/legal-lens/frontend/;
        try_files $uri $uri/ /legallens/index.html;
        index index.html;
    }

    location /legallens/api/ {
        proxy_pass http://127.0.0.1:8767/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;  # search 首次加载 embedding 模型需 30s+
    }

    # 其他项目 ...
}
```

### 2. 启用 + 重载

```bash
sudo ln -s /etc/nginx/sites-available/legallens /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 3. 文件权限

```bash
# scp -r 留下的 700 权限需要修复为 755
chmod -R 755 /opt/legal-lens/frontend/
```

---

## 四、systemd 服务（开机自启）

`/etc/systemd/system/legallens.service`:

```ini
[Unit]
Description=金睛 RiskLens Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/legal-lens/backend
Environment="HF_ENDPOINT=https://hf-mirror.com"
Environment="HF_HUB_OFFLINE=1"
ExecStart=/opt/legal-lens/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8767
Restart=always
RestartSec=10
StandardOutput=append:/opt/legal-lens/storage/logs/uvicorn.log
StandardError=append:/opt/legal-lens/storage/logs/uvicorn.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable legallens
sudo systemctl start legallens
sudo systemctl status legallens
```

---

## 五、运维操作

### 5.1 停服

```bash
# uvicorn (PID 在日志里)
pkill -f 'uvicorn.*8767'
# 或 systemd
sudo systemctl stop legallens
```

### 5.2 重置知识库

```bash
# ⚠️ 必须先停 uvicorn（Qdrant local 模式单进程锁）
pkill -f 'uvicorn.*8767'
sleep 2

# 删 Qdrant + SQLite
rm -rf storage/qdrant
rm -f storage/documents.db

# 重新入库
cd backend
python scripts/local_full_ingest.py

# 重启
cd ..
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8767 \
    > storage/logs/uvicorn.log 2>&1 &
```

### 5.3 单独跑一条用例

```bash
cd backend
python -c "
from app.services.agents import run_analysis
result = run_analysis('某企业申请 500 万流贷,担保为关联公司股权')
import json
print(json.dumps(result, ensure_ascii=False, indent=2))
"
```

### 5.4 查看日志

```bash
tail -f /opt/legal-lens/storage/logs/uvicorn.log
```

---

## 六、监控指标

| 指标 | 正常范围 | 异常处理 |
|------|---------|---------|
| 内存 | < 1.2 GB | 1.6 GB 总内存，并行进程会 OOM |
| CPU | < 80% | 启动后 embedding 加载可达 100% (1-2 分钟) |
| 首次 search 响应 | 30-60s | 加载 embedding 模型，正常 |
| 后续 search 响应 | 1-3s | 异常则查 Qdrant |
| uvicorn 进程数 | 1 | 多余则查 main.py 配置 |

---

## 七、常见问题

### Q1: 报 `set_payload() missing 1 required positional argument: 'points'`
**A**: Qdrant local 模式已知 bug，但实际 set_payload 已生效。可忽略该报错，验证方式：
```bash
curl -X POST http://127.0.0.1:8767/api/knowledge/search -d '{"query":"信托"}' -H 'Content-Type: application/json'
# 返回结果的 category 字段应该都是 "law"
```

### Q2: 报 `RuntimeError: Numpy is not available`
**A**: numpy 2.x 兼容问题，确保：
```bash
pip install --break-system-packages "numpy<2"
```

### Q3: 报 `Qdrant locked`
**A**: 多个进程同时访问 Qdrant。停掉 uvicorn，再跑 ingestion。

### Q4: 首次 search 超时
**A**: embedding 模型首次加载需 30s+。在 nginx 配置里加 `proxy_read_timeout 300s;`。

### Q5: 上传文档后无 chunks
**A**: 检查 `storage/documents.db` 的 `documents` 表，确认 status='ready'，chunks > 0。

---

## 八、备份与恢复

### 8.1 备份

```bash
# 数据 (Qdrant + SQLite)
tar czf legal-lens-backup-$(date +%Y%m%d).tar.gz storage/

# 上传到 OSS / 异地
oss cp legal-lens-backup-*.tar.gz oss://your-bucket/backups/
```

### 8.2 恢复

```bash
# 在新机器
cd /opt/legal-lens
tar xzf legal-lens-backup-20260814.tar.gz

# 启动
cd backend
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8767 \
    > /opt/legal-lens/storage/logs/uvicorn.log 2>&1 &
```

---

## 九、版本升级

```bash
cd /opt/legal-lens
git pull
pkill -f 'uvicorn.*8767'
sleep 2

# 跑迁移（如有）
cd backend
python scripts/migrate.py  # 可选

# 重启
cd ..
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8767 \
    > storage/logs/uvicorn.log 2>&1 &
```

---

## 十、联系方式

- 项目主页：https://github.com/A-yiren/legal-lens
- 提交 Issue：https://github.com/A-yiren/legal-lens/issues
- 联系：7989689965m@gmail.com
