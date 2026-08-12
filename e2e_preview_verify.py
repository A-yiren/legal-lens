"""Playwright 端到端验证：知识库列表 + 预览 modal"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# 强制 UTF-8 输出，避开 PowerShell GBK
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_preview.log")
def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)

OUT_DIR = Path(__file__).parent / "verify-screenshots"
OUT_DIR.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # 1. 知识库页
        log("[1] 访问知识库页")
        await page.goto("https://ayiren.cn/legallens/pages/knowledge-base.html", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)

        # 抓统计
        laws_stat = await page.locator("#stat-laws").text_content()
        chunks_stat = await page.locator("#stat-chunks").text_content()
        vectors_stat = await page.locator("#stat-vectors").text_content()
        log(f"  统计: 法律 {laws_stat} | chunks {chunks_stat} | 向量 {vectors_stat}")

        # 文档总数
        doc_total = await page.locator("#doc-total").text_content()
        log(f"  文档: {doc_total}")

        await page.screenshot(path=str(OUT_DIR / "v3_kb_list.png"), full_page=False)
        log("  [截图] v3_kb_list.png")

        # 滚动到底部再截一张
        await page.evaluate("document.getElementById('doc-list').scrollIntoView()")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "v3_kb_list_scrolled.png"), full_page=False)
        log("  [截图] v3_kb_list_scrolled.png")

        # 2. 点第一个眼睛按钮 -> 弹预览 modal
        log("[2] 点击第一个预览按钮")
        await page.locator("#doc-list button[title='\u9884\u89c8\u5185\u5bb9']").first.click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v3_kb_preview_modal.png"), full_page=False)
        log("  [截图] v3_kb_preview_modal.png")

        # 抓 modal 内容
        title = await page.locator("#preview-title").text_content()
        content = await page.locator("#preview-content").text_content()
        footer = await page.locator("#preview-footer").text_content()
        log(f"  Modal 标题: {title}")
        log(f"  Modal 内容前 150 字: {content[:150] if content else '(空)'}")
        log(f"  Modal footer: {footer}")

        # 3. 关闭 modal
        await page.locator("#preview-modal button:has-text('\u5173\u95ed')").click()
        await page.wait_for_timeout(500)

        # 4. 检索测试
        log("[3] 检索 '醉驾'")
        await page.locator("#search-input").fill("\u9189\u9a7e")
        await page.locator("#do-search").click()
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(OUT_DIR / "v3_kb_search.png"), full_page=False)
        log("  [截图] v3_kb_search.png")

        # 5. 主页 dashboard
        log("[4] 访问主页")
        await page.goto("https://ayiren.cn/legallens/", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT_DIR / "v3_home.png"), full_page=False)
        log("  [截图] v3_home.png")

        await browser.close()
        log("\nDONE")


asyncio.run(main())
