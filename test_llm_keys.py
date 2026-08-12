"""测试 LLM API key"""
import os
import sys
import httpx

keys_to_test = [
    ("key1 (aipath .env)", "sk-cp-FjgrlPMkSJpRMhNWbkEqMT2BzpmVPPH3vZFzb1R76F-VcHR153C9ywmnlkGRNEWbE6PAYpSQSI4PbxzNWuaTa_nsJlZ_n8BR-2ZTXnH4PgZviNNIxzgbEsE"),
    ("key2 (aipath app .env)", "sk-cp-1sR21Z4OkTlNE0Emgy_UW6qH-VWayYoJuIqnjkkUnptZvuUpR2rh5Nad-4IUnpu0k3Prasj4WvZxSTRnYB4WFHoBB1AyvRqg5JNWV-PMieum76JEnXmTgvA"),
]

# 测试两个 base_url
base_urls = [
    "https://api.minimax.chat/v1",
    "https://api.minimaxi.com/v1",
]

for name, key in keys_to_test:
    for base in base_urls:
        print(f"\n--- Testing {name} @ {base} ---")
        try:
            with httpx.Client(timeout=15) as client:
                # 用 chat completion 测
                resp = client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": "MiniMax-Text-01",
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                    },
                )
                print(f"  status: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    print(f"  ✓ OK! response: {msg[:50]!r}")
                    print(f"  model: {data.get('model')}")
                    print(f"  usage: {data.get('usage', {})}")
                else:
                    print(f"  ✗ FAIL: {resp.text[:200]}")
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
