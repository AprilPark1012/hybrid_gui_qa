"""真角色切换 · 特性验证（P22 批 3 · V2a）—— 真浏览器 + 真 demo + **真登录**。

验的是什么（框架能力组合在真环境可用，不是 demo 的功能测试）：
  (1) **1a**：探针（含可展开容器补探）能从隐藏菜单里拿到「切换为订单管理员」语义名；
  (2) **1b 的机制前提**：点它之后页面确实 `location.reload()`，**等页面就绪**才读得到新角色
     （不等就会读到旧角色 —— 这正是缺口 1b 的伤害）；
  (3) **跨页保持新身份**：切完再 goto 业务页，仍是订单管理员（token 走 localStorage）；
  (4) **1c**：置灰按钮常规点击会被 Playwright 拒 -> 需要 force 才点得动、点了才有提示
     （这条同时证明 demo 「置灰但仍可点」的口径：不是真 disabled）。
  **负向**：不做切换时角色不变（证明"变化"确实来自切换动作，不是页面自己变）。

[!] 分工：本脚本验**能力与机制**；「生成物里 `_wait_after_action` 真生效」由批 5 的场景链路
（`cli explore → generate → run`）覆盖 —— 两处都绿才算这条链路通。

跑法（需要 demo 在 8000 上：`python -m demo.app`）：
    python tests/特性2-语义识别与分层定位/verify_role_switch_click.py
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
SUPER = ("super", "super@123")
WANT_ITEM = "切换为订单管理员"
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
    except Exception:                                          # noqa: BLE001
        return -1
    return -1


def main() -> int:
    try:
        with urllib.request.urlopen(DEMO + "/api/health", timeout=5) as r:
            r.read()
    except Exception as e:                                     # noqa: BLE001
        print(f"[NG] 被测 demo 不可达（{DEMO}）——先跑：python -m demo.app  [{e}]")
        return 2

    mem = mem_available_mb()
    print(f"[内存] MemAvailable = {mem if mem >= 0 else '未测'} MB（跑浏览器需要 ≥{MIN_MEM_MB} MB）")
    if 0 <= mem < MIN_MEM_MB:
        print("SKIP：内存不够（如实跳过，不报假绿）→ exit 3")
        return 3 if not fails else 1

    from playwright.sync_api import sync_playwright               # noqa: PLC0415
    from framework.tools.common.browser import launch_opts        # noqa: PLC0415
    from framework.tools.probe.probe import probe_page            # noqa: PLC0415
    from framework.tools.probe.expandable import expand_and_collect  # noqa: PLC0415

    def _ready(page, timeout=8000):
        page.wait_for_function("() => document.body.dataset.hybridReady === '1'", timeout=timeout)

    def _role_text(page) -> str:
        el = page.locator("#nav-user .nu-who")
        return el.inner_text() if el.count() == 1 else ""

    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        ctx = b.new_context()
        pg = ctx.new_page()

        # ---- (1) 真登录（走登录页，不走 ?demo_role= 直连）----
        pg.goto(DEMO + "/login.html", wait_until="domcontentloaded")
        pg.get_by_placeholder("请输入账号").fill(SUPER[0])
        pg.get_by_placeholder("请输入密码").fill(SUPER[1])
        pg.get_by_role("button", name="登 录").click()
        # [!] 不能用 networkidle：本 demo 页面里的 fetch 在 Chromium 侧会挂着不 finished
        #（实测 login.html 的 /api/me -> networkidle 永不达成 -> 30s 超时）。等就绪契约。
        try:
            _ready(pg, timeout=10000)
        except Exception:                                      # noqa: BLE001
            pass
        check(pg.url.find("login") < 0, "正向：真登录后已离开登录页", pg.url)
        check("超级管理员" in _role_text(pg), "正向：右上角显示「超级管理员」", _role_text(pg))

        # ---- (2) 1a：探针能拿到隐藏菜单里的切换项 ----
        base = probe_page(pg)
        extra = expand_and_collect(pg, base)
        names = {(it.get("semantic_name") or "") + "|" + (it.get("name") or "") for it in extra}
        got = [n for n in names if WANT_ITEM in n]
        check(bool(got), f"1a：探针从隐藏菜单里拿到「{WANT_ITEM}」", f"{got[:2]}")

        before = _role_text(pg)

        # ---- (3) 1b 负向对照：不切换 -> 角色不变 ----
        pg.click("#nu-avatar")
        pg.wait_for_timeout(200)
        check(_role_text(pg) == before, "负向：只展开菜单、不选切换项 -> 角色不变（变化来自切换动作）",
              f"{before!r} → {_role_text(pg)!r}")

        # ---- (4) 真切角色 + 等页面就绪（1b 的机制前提）----
        pg.locator('#nu-menu [data-switch="order_admin"]').click()
        # [!] 口径 = 「先确认导航发生、再等就绪」（框架唯一实现，与生成物同一份）：
        # 朴素地直接等 ready 标记会被**旧文档**的现成标记立刻满足 -> 读到切换**前**的角色
        #（第一版就是这么红的：切完读 = 超级管理员，而再 goto 一次 = 订单管理员）。
        from framework.tools.run.waits import wait_after_action
        nav = wait_after_action(pg, probe_ms=3000)
        check(nav, "1b：切换动作确实触发了主框架导航/重载（naive 等 ready 会被旧文档骗过）")
        after = _role_text(pg)
        check("订单管理员" in after, "1b：切换后（等就绪再读）右上角变「订单管理员」", f"{before!r} → {after!r}")
        check(after != before, "1b：角色确实发生了变化（不是等着等着还是旧值）")

        # ---- (5) 跨页保持新身份 ----
        pg.goto(DEMO + "/orders.html")
        try:
            _ready(pg)
        except Exception:                                      # noqa: BLE001
            pass
        check("订单管理员" in _role_text(pg), "跨页：goto 业务页后仍是订单管理员（身份未掉）", _role_text(pg))
        btn = pg.locator("#btn-new-order")
        check(btn.count() == 1 and btn.get_attribute("aria-disabled") != "true",
              "1c：订单管理员身份下「+ 新建订单」**不再置灰**（可用）",
              btn.get_attribute("aria-disabled") if btn.count() else "(无按钮)")

        # ---- (6) 1c 负向：超管（未切换）时置灰 + 常规点击点不动 + force 点才有提示 ----
        pg2 = ctx.new_page()
        pg2.goto(DEMO + "/orders.html?demo_role=super_admin", wait_until="domcontentloaded")
        try:
            _ready(pg2)
        except Exception:                                      # noqa: BLE001
            pass
        b2 = pg2.locator("#btn-new-order")
        check(b2.get_attribute("aria-disabled") == "true", "1c 负向：超管未切换 -> 按钮置灰（aria-disabled）")
        normal_click_blocked = False
        try:
            b2.click(timeout=2500)
        except Exception:                                      # noqa: BLE001
            normal_click_blocked = True
        check(normal_click_blocked,
              "1c 关键事实：置灰按钮**常规点击会被 Playwright 拒绝**（这就是探测期需要 force 的原因）")
        b2.click(force=True, timeout=3000)
        pg2.wait_for_timeout(300)
        tip = pg2.locator("#demo-tip")
        check(tip.count() == 1 and tip.is_visible() and "订单管理员" in tip.inner_text(),
              "1c：force 点击后弹出提示（说明该切哪个角色）—— 置灰≠真 disabled",
              tip.inner_text()[:36] if tip.count() else "(无提示)")
        pg2.close()
        pg.close()
        b.close()

    print()
    if fails:
        print(f"[NG] {len(fails)} 条判据不符预期：")
        for f in fails:
            print(f"   · {f}")
        return 1
    print("全部符合预期 [OK]（真登录 · 隐藏菜单可探 · 切换后等就绪读到新角色 · 跨页保身份 · 置灰需 force）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
