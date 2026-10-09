"""动作后置校验 · 真实页面验证（真浏览器 + 真 demo + 真登录）。

验的是什么（框架能力在真环境可用，不是 demo 的功能测试）：
  (1) **正向**：订单详情页进编辑态、新增一行后（**有未保存的修改**）点「提交」
      -> 框架必须**当场**报出「拒绝提示」并把页面原文回读出来。
      demo 的实现是 `if (this.dirty) { status='页面有未保存的修改...'; return; }`
      —— 不发请求、不报错，靠 `_act` 只记"做了"根本发现不了（这就是被埋三层的那类根因）。
  (2) **负向（防误伤）**：另一张单上只进编辑态、**不改任何东西**就点「提交」
      -> 不该出现任何「动作后置校验」告警（误报会让人把这个能力关掉）。

[!] 为什么要用**两张单子**：提交会改变订单状态（已新建 -> 履行中），
    在同一张单上先测正向再测负向会互相污染（实测踩过：正向造出的 dirty 一直留着，
    导致负向那次提交也被拒 -> 看起来像"误报"，其实是框架判对了）。

跑法（需要 demo 在 8000 上）：python tests/特性9-质量闸门体系/verify_action_effect_check.py
退出码：0 通过 · 1 有失败 · 2 环境不可用 · 3 内存不足 SKIP（SKIP 不是通过）。
"""
from __future__ import annotations

import importlib.util
import json
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
HARNESS = BASE / "scripts" / "generated" / "_harness.py"
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


def _open_orders(n: int = 2) -> list[str]:
    """取 n 张「已新建」（未提交）的订单号 —— 只有这种才有「提交」这个业务动作。"""
    p = BASE / "demo" / ".data" / "state_default.json"
    d = json.load(p.open(encoding="utf-8"))
    orders = d.get("orders") or []
    lines = d.get("lines") or {}
    fulfill = d.get("fulfill") or {}
    cand = [o.get("no") for o in orders
            if (lines.get(o.get("no")) or []) and not (fulfill.get(o.get("no")))]
    return [str(x) for x in cand[-n:]]


def main() -> int:
    try:
        with urllib.request.urlopen(DEMO + "/api/health", timeout=5) as r:
            r.read()
    except Exception as e:                                     # noqa: BLE001
        print(f"[NG] 被测 demo 不可达（{DEMO}）——先跑：python -m demo.app  [{e}]")
        return 2

    mem = mem_available_mb()
    print(f"[内存] MemAvailable = {mem if mem >= 0 else '未测'} MB（跑浏览器需要 >= {MIN_MEM_MB} MB）")
    if 0 <= mem < MIN_MEM_MB:
        print("SKIP：内存不够（如实跳过，不报假绿）-> exit 3")
        return 3 if not fails else 1

    if not HARNESS.exists():
        print(f"[NG] 生成物不存在：{HARNESS} —— 先跑 python -m framework.cli generate")
        return 2

    nos = _open_orders(2)
    print(f"[样本] 未提交订单：{nos}")
    if len(nos) < 2:
        print("[NG] demo 里可用（未提交）订单不足 2 张，无法分离正/负向")
        return 2

    from playwright.sync_api import sync_playwright               # noqa: PLC0415
    from framework.tools.common.browser import launch_opts        # noqa: PLC0415

    spec = importlib.util.spec_from_file_location("_hybrid_harness", HARNESS)
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)

    captured: list[tuple[str, str]] = []
    h._log = lambda page, level, msg: captured.append((str(level), str(msg)))   # noqa: SLF001

    def _ready(page, timeout=8000):
        try:
            page.wait_for_function("() => document.body.dataset.hybridReady === '1'", timeout=timeout)
        except Exception:                                      # noqa: BLE001
            pass

    def _open_detail(ctx, no):
        pg = ctx.new_page()
        pg.goto(f"{DEMO}/order_detail.html?no={no}", wait_until="domcontentloaded")
        _ready(pg)
        return pg

    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        ctx = b.new_context()
        pg = ctx.new_page()

        # ---- 真登录 + 切订单管理员（提交需要 create_order 权限）----
        pg.goto(DEMO + "/login.html", wait_until="domcontentloaded")
        pg.get_by_placeholder("请输入账号").fill(SUPER[0])
        pg.get_by_placeholder("请输入密码").fill(SUPER[1])
        pg.get_by_role("button", name="登 录").click()
        _ready(pg, 10000)
        pg.click("#nu-avatar")
        pg.locator('#nu-menu [data-switch="order_admin"]').click()
        h._wait_after_action(pg)                                # 与生成物同一份等待实现
        print(f"  [信息] 自检：登录已发出写请求（请求监听生效）= {h._write_count(pg) > 0}")

        # ================= 负向（防误伤）：进编辑态但不改任何东西 -> 提交应当真发出 =========
        pg2 = _open_detail(ctx, nos[0])
        h._act(pg2, "click", semantic="编辑", primary=lambda q: q.get_by_role("button", name="编辑"))
        captured.clear()
        w0 = h._write_count(pg2)
        h._act(pg2, "click", semantic="提交", primary=lambda q: q.get_by_role("button", name="提交"))
        alarms_neg = [m for (lv, m) in captured if "动作后置校验" in m]
        check(not alarms_neg,
              "负向：没有未保存修改时点「提交」-> 不告警（误报会让人把能力关掉）",
              (str(alarms_neg[:1])[:120] if alarms_neg else "干净"))
        check(h._write_count(pg2) > w0,
              "负向：这次「提交」确实发出了写请求（POST /api/order/submit）—— 证明判据是看真实效果，不是拍脑袋",
              f"写请求 {w0} -> {h._write_count(pg2)}")
        pg2.close()

        # ================= 正向：新增一行（有未保存修改）-> 提交必须当场报拒绝 =========
        pg3 = _open_detail(ctx, nos[1])
        h._act(pg3, "click", semantic="编辑", primary=lambda q: q.get_by_role("button", name="编辑"))
        h._act(pg3, "click", semantic="新增行", primary=lambda q: q.get_by_role("button", name="新增行"))
        captured.clear()
        h._act(pg3, "click", semantic="提交", primary=lambda q: q.get_by_role("button", name="提交"))
        alllog = [m for (lv, m) in captured]
        refusals = [m for m in alllog if "拒绝提示" in m]
        check(bool(refusals),
              "正向：有未保存修改时点「提交」，框架**当场**报出「拒绝提示」（这正是被埋三层的那类根因）",
              (refusals[0][:130] if refusals else f"captured={alllog[:2]}"))
        check(any("未保存" in m for m in refusals),
              "正向：**原样回读**了页面提示文案（一眼看到根因，不用人肉溯源）",
              (refusals[0][:90] if refusals else ""))
        pg3.close()

        pg.close()
        b.close()

    print()
    if fails:
        print(f"[NG] {len(fails)} 条判据不符预期：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("全部符合预期 [OK]（不改就提交 -> 真发出写请求且不告警；有未保存修改就提交 -> 当场报拒绝并回读原文）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
