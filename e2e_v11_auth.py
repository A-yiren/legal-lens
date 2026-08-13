"""v11: 端到端测试登录流程"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_v11.log")
def log(msg):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)

OUT = Path(__file__).parent / "verify-screenshots"
OUT.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await ctx.new_page()

        # 1. 无 token 访问受保护页面 → 跳 login
        log("[1] 无 token 访问 /legallens/ → 应跳 login")
        await page.goto("https://ayiren.cn/legallens/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        log(f"  当前 URL: {page.url}")
        if "/pages/login.html" in page.url:
            log("  ✓ 路由保护生效")
        else:
            log(f"  ✗ 没跳到 login（{page.url}）")
        await page.screenshot(path=str(OUT / "v11_login_page.png"), full_page=False)
        log("  [截图] v11_login_page.png")

        # 2. 在 login 页注册新用户
        log("\n[2] 注册新用户 wang_lawyer")
        await page.locator("#tab-register").click()
        await page.wait_for_timeout(500)
        # 用一个随机用户名避免冲突
        import time
        uname = f"lawtest{int(time.time()) % 100000}"
        await page.locator("#register-form input[name='username']").fill(uname)
        await page.locator("#register-form input[name='display_name']").fill("王律师测试")
        await page.locator("#register-form input[name='email']").fill(f"{uname}@example.com")
        await page.locator("#register-form input[name='password']").fill("TestPass123!")
        await page.locator("#register-form input[name='password2']").fill("TestPass123!")
        await page.screenshot(path=str(OUT / "v11_register_filled.png"), full_page=False)
        log(f"  填表完成（username={uname}）")
        log(f"  [截图] v11_register_filled.png")

        await page.locator("#register-btn").click()
        log("  提交...")
        # 等跳走
        try:
            await page.wait_for_url("**/index.html", timeout=20000)
            log("  ✓ 跳到首页")
        except Exception as e:
            log(f"  ✗ 跳首页失败: {e}")
        await page.wait_for_timeout(2000)
        log(f"  当前 URL: {page.url}")
        await page.screenshot(path=str(OUT / "v11_home_after_register.png"), full_page=False)
        log(f"  [截图] v11_home_after_register.png")

        # 3. localStorage 应有 token
        token = await page.evaluate("() => localStorage.getItem('legallens_token')")
        user = await page.evaluate("() => localStorage.getItem('legallens_user')")
        log(f"  token: {'✓' if token else '✗'} (前 30: {(token or '')[:30]})")
        log(f"  user: {user[:80] if user else '✗'}")

        # 4. 访问其他受保护页面（不再跳 login）
        log("\n[4] 访问受保护页面 /case-analysis.html")
        await page.goto("https://ayiren.cn/legallens/pages/case-analysis.html",
                        wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        log(f"  当前 URL: {page.url}")
        if "/pages/case-analysis.html" in page.url:
            log("  ✓ 已登录可访问")
        await page.screenshot(path=str(OUT / "v11_protected_page.png"), full_page=False)
        log(f"  [截图] v11_protected_page.png")

        # 5. 退出登录
        log("\n[5] 退出登录")
        # 找退出按钮
        logout = page.locator("[data-action='logout']")
        if await logout.count() > 0:
            await logout.first.click()
            log("  点退出")
        else:
            log("  ✗ 找不到退出按钮")
        await page.wait_for_timeout(3000)
        log(f"  退出后 URL: {page.url}")
        token2 = await page.evaluate("() => localStorage.getItem('legallens_token')")
        log(f"  token 已清: {'✓' if not token2 else '✗'}")

        await browser.close()
        log("\nDONE")


asyncio.run(main())
