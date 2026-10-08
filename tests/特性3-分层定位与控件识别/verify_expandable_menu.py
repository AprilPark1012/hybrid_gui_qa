"""可展开菜单探针 · 特性验证（P22 批 1 · V1）—— 真浏览器 + 真 demo。

验的是什么（框架特性，不是 demo 功能）：
  (1) 探针必须能收到**藏在 display:none 菜单里**的可点元素（角色切换项）—— 缺口 1a 的解药；
  (2) 探测是**只读动作**：探完菜单必须被关掉（否则后面的步骤会被展开的菜单挡住 —— 这是
     `_close_open_modal` 那条纪律的同类要求）；
  (3) **负向自证**：关掉展开开关时清单里**不该**有菜单项 -> 证明"能收到"确实来自展开动作，
     而不是页面本来就可见（不然这条判据是恒真的假绿）。

跑法（需要 demo 在 8000 上：`python -m demo.app`）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python tests/特性3-分层定位与控件识别/verify_expandable_menu.py        # 期望最后一行：全部符合预期 [OK]
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
# 角色菜单里的三个切换项（auth.js::mountTopbar 渲染的 nu-item 文案）——
# 只断言「订单管理员」这条：本场景必需的那一个（其余两条的存在性断言原在 demo 需求侧验证里覆盖，该批验证已按 2026-10-07 口径删除）
WANT_MENU_ITEM = "切换为订单管理员"
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
        return -1                                              # 拿不到 -> 如实"未测"，不据此 SKIP
    return -1


def names_of(items: list[dict]) -> set[str]:
    """语义名 + 可读名都收 —— 判据只关心「AI 能不能引用到那一项」。"""
    out: set[str] = set()
    for it in items:
        for k in ("semantic_name", "name"):
            v = (it.get(k) or "").strip()
            if v:
                out.add(v)
    return out


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
        print("SKIP：内存不够，未跑浏览器判据（如实跳过，不报假绿）→ exit 3")
        return 3 if not fails else 1

    from playwright.sync_api import sync_playwright               # noqa: PLC0415
    from framework.tools.common.browser import launch_opts        # noqa: PLC0415
    from framework.tools.probe.probe import probe_page            # noqa: PLC0415
    from framework.tools.probe.expandable import expand_and_collect  # noqa: PLC0415

    def _ready(page, timeout=8000):
        page.wait_for_function("() => document.body.dataset.hybridReady === '1'", timeout=timeout)

    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        ctx = b.new_context()
        pg = ctx.new_page()
        # 用超管身份直连（本判据验的是**探针特性**，不把登录流程混进来；
        # 登录→切角色的**真链路**由 verify_role_switch_click.py 负责）
        pg.goto(DEMO + "/orders.html?demo_role=super_admin", wait_until="networkidle")
        _ready(pg)

        base = probe_page(pg)
        base_names = names_of(base)
        print(f"[探针] 基础采集 {len(base)} 项（未展开菜单）")
        check(not any(WANT_MENU_ITEM in n for n in base_names),
              "前置事实：菜单项在**未展开**时不可见（探针基础采集拿不到它）",
              f"{WANT_MENU_ITEM} 命中={any(WANT_MENU_ITEM in n for n in base_names)}")

        # ---- (1) 展开后必须收到菜单项 ----
        extra = expand_and_collect(pg, base, enabled=True)
        extra_names = names_of(extra)
        check(any(WANT_MENU_ITEM in n for n in extra_names),
              f"正向：展开菜单后探针收到「{WANT_MENU_ITEM}」（缺口 1a 的解药）",
              f"新增 {len(extra)} 项：{sorted(extra_names)[:6]}")
        check(len(extra) >= 3,
              "正向：三个角色切换项 + 其余菜单项都被收到（不是只捞到一条）",
              f"新增 {len(extra)} 项")

        # ---- (2) 探完必须关掉（探测 = 只读动作，不许留副作用）----
        menu = pg.locator("#nu-menu")
        visible = menu.count() == 1 and menu.is_visible()
        check(not visible, "正向：探完菜单**已关闭**（探测不留副作用，后续步骤不被挡住）",
              f"#nu-menu visible={visible}")
        # 关不掉也别假绿：再试一次点击，仍开着就如实报
        if visible:
            pg.click("#nu-avatar", force=True)
            pg.wait_for_timeout(200)

        # ---- (3) 负向自证：关掉展开开关 -> 不该收到（证明(1)不是恒真）----
        pg2 = ctx.new_page()
        pg2.goto(DEMO + "/orders.html?demo_role=super_admin", wait_until="networkidle")
        _ready(pg2)
        base2 = probe_page(pg2)
        off = expand_and_collect(pg2, base2, enabled=False)
        off_names = names_of(off)
        check(not any(WANT_MENU_ITEM in n for n in off_names),
              "负向：关闭展开开关 -> 清单里没有菜单项（证明正向那条不是恒真的假绿）",
              f"新增 {len(off)} 项")
        pg2.close()
        pg.close()
        b.close()

    print()
    if fails:
        print(f"[NG] {len(fails)} 条判据不符预期：")
        for f in fails:
            print(f"   · {f}")
        return 1
    print("全部符合预期 [OK]（隐藏菜单能探到 · 探完会关 · 关掉开关就收不到）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
