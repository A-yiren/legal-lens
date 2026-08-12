#!/bin/bash
# 启动律瞳 LegalLens
cd /opt/legal-lens
export HF_ENDPOINT=https://hf-mirror.com
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8767
