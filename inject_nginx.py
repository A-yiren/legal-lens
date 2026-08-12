#!/usr/bin/env python3
"""把 legallens location 块注入到 ayiren.cn nginx server 块里"""
import re

NGINX_CONF = "/etc/nginx/sites-enabled/ayiren.cn"
NEW_BLOCK_PATH = "/tmp/nginx_legallens_block.txt"

txt = open(NGINX_CONF, encoding="utf-8").read()
new_block = open(NEW_BLOCK_PATH, encoding="utf-8").read()

# 找 "location /api/" 开头的块，定位到块结束 "}"
m = re.search(r"location /api/.*?\n\s*\}", txt, re.DOTALL)
if not m:
    print("ERR: not found /api/ location block")
    raise SystemExit(1)

# 备份
import shutil
shutil.copy(NGINX_CONF, NGINX_CONF + ".bak." + str(__import__("time").time()))

# 插入
insert_pos = m.end()
new_txt = txt[:insert_pos] + new_block + txt[insert_pos:]
open(NGINX_CONF, "w", encoding="utf-8").write(new_txt)
print(f"OK: inserted at pos {insert_pos}, total len {len(new_txt)}")
