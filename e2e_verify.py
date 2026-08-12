"""端到端验收 - 模拟用户实际操作"""
import asyncio
from playwright.async_api import async_playwright

URL_BASE = "https://ayiren.cn/legallens"
PAGES = [
    ("home", "/"),
    ("case-analysis", "/pages/case-analysis.html"),
    ("case-list", "/pages/case-list.html"),
    ("knowledge-base", "/pages/knowledge-base.html"),
    ("obsidian", "/pages/obsidian.html"),
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        results = []

        # 1. 加载每个页面，看 console 报错 + 截图
        for name, path in PAGES:
            page = await ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(f"PAGE_ERR: {e}"))
            page.on("console", lambda m: m.type == "error" and errors.append(f"CONSOLE: {m.text}"))
            try:
                resp = await page.goto(URL_BASE + path, wait_until="networkidle", timeout=20000)
                status = resp.status if resp else 0
                title = await page.title()
                # 等 2 秒让动态内容（fetch API）加载
                await page.wait_for_timeout(2000)
                shot = f"C:\\Users\\34464\\.mavis\\agents\\mavis\\workspace\\legal-lens\\e2e_{name}.png"
                await page.screenshot(path=shot, full_page=False)
                results.append((name, status, title, errors, shot))
            except Exception as e:
                results.append((name, 0, str(e)[:80], errors, ""))
            await page.close()

        # 2. 实操：点"试用示例案情" → 触发 LLM 分析 → 截图结果
        page = await ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"PAGE_ERR: {e}"))
        try:
            await page.goto(URL_BASE + "/pages/case-analysis.html", wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(1000)
            # 点"试用示例案情"按钮
            await page.click("#try-example", timeout=5000)
            # 输入框会被填入示例
            case_text = await page.input_value("#case-input")
            print(f"\n  填入案情: {case_text[:60]}...")
            # 点"开始 AI 分析"
            await page.click("#analyze-btn", timeout=5000)
            print("  等待 AI 分析...")
            # 等待 result-state 出现
            try:
                await page.wait_for_selector("#result-state:not(.hidden)", timeout=180000)
                print("  ✓ AI 分析完成")
                # 截图
                shot = f"C:\\Users\\34464\\.mavis\\agents\\mavis\\workspace\\legal-lens\\e2e_analysis_done.png"
                await page.screenshot(path=shot, full_page=False)
                # 拿数据
                focus = await page.locator("#result-state").text_content()
                print(f"  结果前 300 字符: {focus[:300]}")
            except Exception as e:
                print(f"  ✗ 等待超时: {e}")
                shot = f"C:\\Users\\34464\\.mavis\\agents\\mavis\\workspace\\legal-lens\\e2e_analysis_fail.png"
                await page.screenshot(path=shot, full_page=False)
        except Exception as e:
            print(f"  操作失败: {e}")
        await page.close()

        await browser.close()

        # 汇总
        print("\n" + "=" * 60)
        print("验收报告")
        print("=" * 60)
        for name, status, title, errs, shot in results:
            err_str = f" | 错误: {errs}" if errs else ""
            print(f"  [{status}] {name:20s} {title[:30]}{err_str}")
        if errors:
            print(f"\n  实操错误: {errors[:3]}")


asyncio.run(main())
