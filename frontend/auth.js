/**
 * 律瞳 LegalLens - 全局认证脚本
 * 所有受保护页面都应引用本脚本
 *
 * 用法: <script src="../auth.js"></script> (pages 目录)
 *      <script src="auth.js"></script> (根目录)
 *
 * 功能:
 * 1. 检查 localStorage 里的 token，没 token 跳 login.html
 * 2. 在 sidebar 底部注入"退出登录"按钮
 * 3. 提供 getToken() / getUser() 辅助函数
 * 4. 401 自动清 token 跳 login
 */

(function () {
    const API_BASE = "/legallens";
    const TOKEN_KEY = "legallens_token";
    const USER_KEY = "legallens_user";

    // ===== Token 管理 =====
    function getToken() {
        return localStorage.getItem(TOKEN_KEY);
    }
    function getUser() {
        try {
            return JSON.parse(localStorage.getItem(USER_KEY) || "null");
        } catch {
            return null;
        }
    }
    function clearAuth() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    }
    window.LegalLensAuth = { getToken, getUser, clearAuth, API_BASE };

    // ===== 路由保护 =====
    const here = window.location.pathname;
    const isLoginPage = here.endsWith("/pages/login.html") || here.endsWith("/login.html");
    if (isLoginPage) return; // 登录页自身不需要 token

    const token = getToken();
    if (!token) {
        // 计算相对 login.html 的路径
        let loginPath = "pages/login.html";
        if (here.includes("/pages/")) {
            loginPath = "login.html";
        }
        window.location.replace(loginPath);
        return;
    }

    // ===== 注入退出按钮 =====
    function injectLogoutButton() {
        // 找 sidebar 底部"王律师"区域
        const candidates = document.querySelectorAll("aside .p-3.border-t, aside .p-4.border-t");
        if (candidates.length === 0) return;
        const container = candidates[0];

        const user = getUser();
        const display = user ? (user.display_name || user.username) : "已登录";

        // 替换 / 包装：在原有"王律师"区域下方加一个退出按钮
        const logoutDiv = document.createElement("div");
        logoutDiv.className = "mt-2 flex items-center justify-between gap-2 px-2 py-1.5 text-xs text-stone-500 hover:text-rose-600 hover:bg-rose-50 rounded transition cursor-pointer";
        logoutDiv.innerHTML = `
            <span class="truncate">${escapeHtml(display)}</span>
            <span class="inline-flex items-center gap-1" data-action="logout">
                <i class="fa-solid fa-right-from-bracket"></i>退出
            </span>
        `;
        logoutDiv.addEventListener("click", doLogout);
        container.appendChild(logoutDiv);

        // 改原"王律师"行（如果存在）为只读样式
        const userRow = container.querySelector(".flex.items-center.gap-3.px-2.py-2");
        if (userRow) {
            userRow.style.opacity = "0.5";
            userRow.style.cursor = "default";
        }
    }

    async function doLogout() {
        const t = getToken();
        if (t) {
            try {
                await fetch(`${API_BASE}/api/auth/logout`, {
                    method: "POST",
                    headers: { "Authorization": `Bearer ${t}` },
                });
            } catch (e) {
                // ignore
            }
        }
        clearAuth();
        const here2 = window.location.pathname;
        let loginPath = "pages/login.html";
        if (here2.includes("/pages/")) {
            loginPath = "login.html";
        }
        window.location.href = loginPath;
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
    }

    // ===== 401 自动清 token 跳 login =====
    const origFetch = window.fetch;
    window.fetch = async function (...args) {
        const res = await origFetch.apply(this, args);
        if (res.status === 401) {
            const url = typeof args[0] === "string" ? args[0] : args[0].url;
            // auth API 自己 401 不跳（避免循环）
            if (!url.includes("/api/auth/")) {
                clearAuth();
                const here3 = window.location.pathname;
                let loginPath = "pages/login.html";
                if (here3.includes("/pages/")) {
                    loginPath = "login.html";
                }
                if (!window.location.pathname.endsWith("/login.html")) {
                    window.location.href = loginPath;
                }
            }
        }
        return res;
    };

    // 注入退出按钮
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", injectLogoutButton);
    } else {
        injectLogoutButton();
    }
})();
