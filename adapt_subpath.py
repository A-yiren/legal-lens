#!/usr/bin/env python3
"""把 legal-lens 前端适配到 https://ayiren.cn/legallens/ 子路径下部署。

做的事：
1. API_BASE 从 "" 改成 "/legallens"
2. 所有 href 链接改成绝对路径 "/legallens/..."
3. 加 favicon + OG meta
4. 移动端 sidebar 适配（折叠）
"""
import re
from pathlib import Path

FRONTEND = Path("/opt/legal-lens/frontend")
BASE = "/legallens"

# 简单的 SVG favicon（深绿底+白色法槌）
FAVICON_SVG = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%230c4a3e'/><text x='50' y='68' font-size='60' text-anchor='middle' fill='white' font-family='serif'>⚖</text></svg>"

# OG meta + 移动端适配 + favicon + 公共 CSS
HEAD_INSERT = f"""
    <link rel="icon" type="image/svg+xml" href="{FAVICON_SVG}">
    <meta name="description" content="律瞳 LegalLens — 律师专属 AI 案件分析平台。基于真实法律条文的 RAG 检索 + 引用溯源。">
    <meta property="og:title" content="律瞳 LegalLens">
    <meta property="og:description" content="律师专属 AI 案件分析平台">
    <meta property="og:type" content="website">
    <meta name="theme-color" content="#0c4a3e">
    <style>
        /* === 移动端适配 === */
        @media (max-width: 768px) {{
            .desktop-sidebar {{ display: none !important; }}
            .mobile-menu-btn {{ display: flex !important; }}
        }}
        @media (min-width: 769px) {{
            .mobile-menu-btn {{ display: none !important; }}
            .mobile-menu-overlay {{ display: none !important; }}
        }}
        .mobile-menu-overlay {{
            display: none;
            position: fixed; inset: 0; z-index: 40;
            background: rgba(0,0,0,0.4);
        }}
        .mobile-menu-overlay.open {{ display: block; }}
        /* === 页面切换动效 === */
        main {{ animation: fadeIn 0.2s ease-out; }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(4px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        /* === 通用细节 === */
        .citation {{ transition: all 0.15s; }}
        button {{ transition: all 0.15s; }}
        a {{ transition: color 0.15s, background-color 0.15s; }}
    </style>
"""

# sidebar 适配：把 w-60 之类的类保留，但加 desktop-sidebar 类方便移动端隐藏
# mobile menu 按钮（每个页面都需要）
MOBILE_BTN = """
        <button class="mobile-menu-btn hidden fixed top-4 left-4 z-50 w-10 h-10 bg-white border border-stone-200 rounded-lg items-center justify-center shadow-sm" onclick="toggleMobileMenu()">
            <i class="fa-solid fa-bars text-stone-700"></i>
        </button>
        <div class="mobile-menu-overlay" onclick="toggleMobileMenu()"></div>
"""

MOBILE_SCRIPT = """
        <script>
            function toggleMobileMenu() {
                const aside = document.querySelector('aside');
                const overlay = document.querySelector('.mobile-menu-overlay');
                if (aside) aside.classList.toggle('open');
                if (overlay) overlay.classList.toggle('open');
            }
        </script>
"""


def adapt_file(path: Path):
    """适配单个 HTML 文件"""
    html = path.read_text(encoding="utf-8")
    original = html

    # 1. API_BASE 改成绝对路径
    html = html.replace('const API_BASE = "";', f'const API_BASE = "{BASE}";')
    # 兜底：万一有不同写法
    html = re.sub(r'const\s+API_BASE\s*=\s*["\'][^"\']*["\'];', f'const API_BASE = "{BASE}";', html)

    # 2. href 改成绝对路径
    # 在 index.html 里：href="index.html" / href="pages/xxx.html"
    if path.name == "index.html":
        html = html.replace('href="index.html"', f'href="{BASE}/index.html"')
        html = html.replace('href="pages/', f'href="{BASE}/pages/')
    else:
        # pages/ 下的文件
        # ../index.html → /legallens/index.html
        html = html.replace('href="../index.html"', f'href="{BASE}/index.html"')
        # 兄弟文件 case-list.html → /legallens/pages/case-list.html
        # 包含 query string 的：case-analysis.html?case_id=xxx
        html = re.sub(r'href="(?!/|#|https?:|mailto:)([a-z][a-z0-9-]*\.html)(\?[^"]*)?"',
                      lambda m: f'href="{BASE}/pages/{m.group(1)}' + (m.group(2) or '') + '"', html)
        # 已经有 /pages/ 前缀的（保险）
        html = html.replace(f'href="{BASE}/pages/pages/', f'href="{BASE}/pages/')

    # 3. 加 head 公共资源（favicon + meta + 自定义 CSS）
    if '<link rel="icon"' not in html:
        html = html.replace('</title>', '</title>\n' + HEAD_INSERT, 1)

    # 4. 给 sidebar 加 desktop-sidebar 类
    html = re.sub(r'<aside class="(w-\d+ bg-white[^"]*)"',
                  r'<aside class="desktop-sidebar \1"', html)

    # 5. 加 mobile menu 按钮（插入到 body 之后第一个 div 之前）
    if 'mobile-menu-btn' not in html:
        html = html.replace('<body class="', MOBILE_BTN + '<body class="', 1)

    # 6. 加 mobile menu 脚本
    if 'toggleMobileMenu' not in html:
        html = html.replace('</body>', MOBILE_SCRIPT + '</body>', 1)

    if html != original:
        path.write_text(html, encoding="utf-8")
        return True
    return False


def main():
    files = [FRONTEND / "index.html"] + sorted((FRONTEND / "pages").glob("*.html"))
    changed = 0
    for f in files:
        if adapt_file(f):
            print(f"  ✓ {f.relative_to(FRONTEND)}")
            changed += 1
        else:
            print(f"  - {f.relative_to(FRONTEND)} (no change)")
    print(f"\n完成: 改了 {changed}/{len(files)} 个文件")


if __name__ == "__main__":
    main()
