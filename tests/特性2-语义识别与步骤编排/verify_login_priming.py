"""场景「登录前置」· 特性验证（P22 批 5 · V4）—— 真浏览器 + 真 demo。

验的是一条**真问题**：demo 加了登录之后，**未登录的上下文去探业务页，探到的是登录页控件**
（2026-09-29 实测：裸跑 `cli probe` 只探到 7 项「账号/密码/登 录」）。
而场景声明 `auth:` 之后，框架能在 context 建好时注入 token -> 探到的才是真业务控件。

判据（负向自证是重点）：
  (1) **负向（先证问题存在）**：不带登录前置访问 `orders.html` -> 页面被踢到 `/login.html`
  (2) **正向**：`ensure_logged_in` 注入后访问同一页 -> 停在业务页 + 探到业务控件（如「订单名称」）
  (3) **负向自证**：把 `token_key` 故意写错 -> 必须回到"被踢到登录页"的状态
     （证明 (2) 的通过**确实来自注入的 token**，而不是页面本来就能开）
  (4) **同源**：auth 声明从**主场景 yml** 读（不在脚本里另写一份，避免两处漂移）

跑法（需要 demo）：python tests/特性2-语义识别与步骤编排/verify_login_priming.py
退出码：0 通过 · 1 有失败 · 2 环境不可用 · 3 内存不足 SKIP（**SKIP 不是通过**）。
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from framework.tools.common.text_io import force_stdio  # noqa: E402

force_stdio()

DEMO = os.environ.get("HYBRID_BASE_URL", "http://localhost:8000").rstrip("/")
MIN_MEM_MB = 550
SCENARIO = BASE / "scenarios" / "orders" / "orders_invoice_full_lifecycle.yml"
WANT_CONTROL = "订单名称"          # 订单列表页搜索区的一个业务控件（登录页绝不会有）
fails: list[str] = []


def check(ok, desc, detail=""):
    print(("  [OK] " if ok else "  [NG] ") + desc + (f"   [{detail}]" if detail else ""))
    if not ok:
        fails.append(desc)


def mem_available_mb() -> int:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except Exception:                                              # noqa: BLE001
        return -1
    return -1


def main() -> int:
    try:
        with urllib.request.urlopen(DEMO + "/api/health", timeout=5) as r:
            r.read()
    except Exception as e:                                         # noqa: BLE001
        print(f"[NG] 被测 demo 不可达（{DEMO}）——先跑：python -m demo.app  [{e}]")
        return 2

    from framework.tools.generate.scenario import load_scenario_file   # noqa: PLC0415
    from framework.tools.run.login import ensure_logged_in, describe    # noqa: PLC0415

    sc = load_scenario_file(SCENARIO)
    spec = sc.auth_spec()
    check(bool(spec), "前置：主场景 yml 里声明了 auth 段（本判据与它同源）", describe(spec))
    check(spec.get("token_key") == "demo_token",
          "前置：token_key 指向 demo 的登录态键（改错了本判据会说清楚）", spec.get("token_key", ""))

    mem = mem_available_mb()
    print(f"[内存] MemAvailable = {mem if mem >= 0 else '未测'} MB（跑浏览器需要 ≥{MIN_MEM_MB} MB）")
    if 0 <= mem < MIN_MEM_MB:
        print("SKIP：内存不够（如实跳过，不报假绿）→ exit 3")
        return 3 if not fails else 1

    from playwright.sync_api import sync_playwright                 # noqa: PLC0415
    from framework.tools.common.browser import launch_opts          # noqa: PLC0415
    from framework.tools.probe.probe import probe_page              # noqa: PLC0415

    def _open(b, install_spec=None, key_override=None):
        """开一个 context（可选注入 token）→ 访问业务页 → 返回 (url, 控件数)。"""
        ctx = b.new_context()
        if install_spec is not None:
            sp = dict(install_spec)
            if key_override is not None:
                sp["token_key"] = key_override
            ensure_logged_in(ctx, DEMO, sp)
        pg = ctx.new_page()
        pg.goto(DEMO + "/orders.html", wait_until="domcontentloaded")
        try:
            pg.wait_for_selector("body[data-hybrid-ready='1']", timeout=8000, state="attached")
        except Exception:                                          # noqa: BLE001
            pg.wait_for_timeout(600)
        n = len(probe_page(pg))
        return pg.url, n, pg

    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))

        # (1) 负向：不登录 -> 被踢到登录页（先证问题真实存在）
        url1, n1, pg1 = _open(b)
        check("login" in url1, "(1) 负向：不带登录前置访问 orders.html -> 被 auth.js 踢到登录页", url1)
        check(n1 <= 15, "(1) 负向：此时探到的是登录页控件（数量很少）", f"{n1} 项")

        # (2) 正向：登录前置 -> 停在业务页 + 探到业务控件
        url2, n2, pg2 = _open(b, install_spec=spec)
        check("login" not in url2, "(2) 正向：登录前置后停在业务页（不再被踢）", url2)
        names2 = {str(it.get("name") or "") for it in probe_page(pg2)}
        hit = [x for x in names2 if WANT_CONTROL in x]
        check(bool(hit), f"(2) 正向：探到业务控件「{WANT_CONTROL}」（登录页绝不会有）",
              f"{n2} 项 · 命中 {hit[:3]}")
        check(n2 > n1, "(2) 正向：控件数明显多于未登录态（业务页 vs 登录页）", f"未登录 {n1} → 登录后 {n2}")

        # (3) 负向自证：token_key 写错 -> 回到未登录（证明 (2) 的通过来自注入的 token）
        url3, n3, pg3 = _open(b, install_spec=spec, key_override="wrong_token_key_p22")
        check("login" in url3, "(3) 负向自证：token_key 写错 -> 又被踢回登录页"
                               "（证明 (2) 确实来自注入的 token）", url3)
        b.close()

    print()
    if fails:
        print(f"[NG] {len(fails)} 条判据不符预期：")
        for f in fails:
            print(f"   · {f}")
        return 1
    print("全部符合预期 [OK]（不登录取不到业务控件 · 登录前置后取到 · 换个键名就失效）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
