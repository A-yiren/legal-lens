"""配置 .env: 用 aipath 的 key + 正确 model + 重启服务 + 端到端测试"""
import os
import sys
import subprocess
import time

ENV_PATH = "/opt/legal-lens/.env"
API_KEY = "sk-cp-FjgrlPMkSJpRMhNWbkEqMT2BzpmVPPH3vZFzb1R76F-VcHR153C9ywmnlkGRNEWbE6PAYpSQSI4PbxzNWuaTa_nsJlZ_n8BR-2ZTXnH4PgZviNNIxzgbEsE"
BASE_URL = "https://api.minimax.chat/v1"
MODEL = "MiniMax-Text-01"

# 读现有 .env
with open(ENV_PATH, 'r') as f:
    lines = f.readlines()

# 替换/添加
new_lines = []
seen = set()
updates = {
    'LLM_API_KEY': API_KEY,
    'LLM_BASE_URL': BASE_URL,
    'LLM_MODEL': MODEL,
}
for line in lines:
    key = line.split('=', 1)[0].strip() if '=' in line else ''
    if key in updates:
        new_lines.append(f"{key}={updates[key]}\n")
        seen.add(key)
        del updates[key]
    else:
        new_lines.append(line)
for k, v in updates.items():
    new_lines.append(f"{k}={v}\n")
    seen.add(k)

with open(ENV_PATH, 'w') as f:
    f.writelines(new_lines)
print(f".env 已更新: {seen}")

# 验证
with open(ENV_PATH) as f:
    for line in f:
        if any(k in line for k in ['LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL']):
            # 隐藏 key 的中段
            if 'KEY' in line:
                k, v = line.strip().split('=', 1)
                print(f"  {k}={v[:15]}...{v[-10:]}")
            else:
                print(f"  {line.strip()}")

# 重启服务
print("\n--- 重启服务 ---")
subprocess.run("ps -ef | grep 'uvicorn.*8767' | grep -v grep | awk '{print $2}' | xargs -r kill 2>/dev/null", shell=True, check=False)
time.sleep(2)
subprocess.Popen(
    "cd /opt/legal-lens/backend && HF_ENDPOINT=https://hf-mirror.com nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8767 > /opt/legal-lens/storage/logs/server.out.log 2>&1 &",
    shell=True,
)
print("已发起新进程")

# 等服务起来
print("\n--- 等待服务启动 ---")
for i in range(15):
    time.sleep(2)
    r = subprocess.run("curl -s --max-time 3 http://127.0.0.1:8767/api/health", shell=True, capture_output=True, text=True)
    if 'vector_count' in r.stdout:
        print(f"  ✓ 服务就绪 (i={i})")
        print(f"  {r.stdout}")
        break
    print(f"  等待中... {i}")
else:
    print("  ✗ 服务启动超时")
    sys.exit(1)
