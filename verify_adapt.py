#!/usr/bin/env python3
"""验证 adapt_subpath.py 改得对不对"""
import re
from pathlib import Path

FRONTEND = Path("/opt/legal-lens/frontend")

for f in [FRONTEND / "index.html"] + sorted((FRONTEND / "pages").glob("*.html")):
    html = f.read_text(encoding="utf-8")
    print(f"\n=== {f.relative_to(FRONTEND)} ===")

    # API_BASE
    m = re.search(r'const\s+API_BASE\s*=\s*["\']([^"\']*)["\']', html)
    print(f"  API_BASE = {m.group(1) if m else 'NOT FOUND'}")

    # href 相对路径应该不存在
    rel_hrefs = re.findall(r'href="(?!/|#|https?:|mailto:|javascript:)([^"]+)"', html)
    print(f"  剩余相对路径 href ({len(rel_hrefs)}): {rel_hrefs[:5]}")

    # favicon / og / mobile 适配
    has_favicon = '<link rel="icon"' in html
    has_mobile = 'mobile-menu-btn' in html
    has_sidebar_cls = 'desktop-sidebar' in html
    print(f"  favicon: {has_favicon}, mobile-btn: {has_mobile}, sidebar-class: {has_sidebar_cls}")
