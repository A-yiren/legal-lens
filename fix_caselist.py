#!/usr/bin/env python3
"""修复 case-list.html 里带 query string 的相对路径"""
from pathlib import Path
p = Path("/opt/legal-lens/frontend/pages/case-list.html")
html = p.read_text(encoding="utf-8")
old = 'href="case-analysis.html?case_id=${c.id}"'
new = 'href="/legallens/pages/case-analysis.html?case_id=${c.id}"'
if old in html:
    html = html.replace(old, new)
    p.write_text(html, encoding="utf-8")
    print("fixed")
else:
    print("not found, already fixed or different")
