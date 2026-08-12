#!/usr/bin/env python3
"""把 seed_data 里坏掉的中文文件名重命名为合法中文"""
import os
import sys

d = '/opt/legal-lens/seed_data'
print("=== before ===")
for f in sorted(os.listdir(d)):
    raw = f.encode('utf-8', errors='replace')
    print(f"  hex: {raw.hex()[:60]}... -> {f!r}")

# 文件名已知三个，先按 hex 内容做映射
# hex 前缀对应:
# d185d09a... = 劳动合同法.md (正确 UTF-8: e58ab3...)
# d186e296... = 民法典-合同编.md
# d187d0af... = 知识产权-专利法.md
mapping = {
    '劳动合同法': '劳动合同法',
    '民法典-合同编': '民法典-合同编',
    '知识产权-专利法': '知识产权-专利法',
}

renamed = 0
for f in os.listdir(d):
    fp = os.path.join(d, f)
    # 尝试按 GBK 解码，看哪个能解出有意义的中文
    try:
        decoded = f.encode('latin-1').decode('utf-8')
    except Exception:
        decoded = None
    print(f"\nfile: {f!r}")
    print(f"  utf-8 decode: {decoded!r}")

    # 简化方案：直接根据已知 hex 前缀对号入座
    raw = f.encode('utf-8', errors='surrogateescape')
    hex_prefix = raw[:3].hex()
    new_name = None
    if hex_prefix == 'd185d0':  # 劳动合同法
        new_name = '劳动合同法.md'
    elif hex_prefix == 'd186e2':  # 民法典
        new_name = '民法典-合同编.md'
    elif hex_prefix == 'd187d0':  # 知识产权
        new_name = '知识产权-专利法.md'

    if new_name and new_name != f:
        new_path = os.path.join(d, new_name)
        if os.path.exists(new_path):
            print(f"  skip: {new_name} already exists")
            continue
        os.rename(fp, new_path)
        renamed += 1
        print(f"  renamed -> {new_name}")

print(f"\n=== done, renamed {renamed} ===")
print("\n=== after ===")
for f in sorted(os.listdir(d)):
    print(f"  {f!r}")
