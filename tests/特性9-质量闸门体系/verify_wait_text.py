"""`wait_text` 等待式断言 · 特性验证（P22 批 4 · V3）—— 真浏览器 + 真 demo。

验的是**生成物里的那份实现**：`generator._render_harness()` 渲染出的 `_harness.py`
（就是交付给用户的同一份代码），而不是在判据里重写一遍等待逻辑
—— 重写就违反单一来源，也验不到真东西。

判据口径：
  (1) 正向 A：目标文本已在页面上 -> **探到就走**（不许白等满超时）
  (2) 正向 B：**服务端新增数据、页面自己不会刷新** -> `refresh=research` 每轮重放搜索 -> 等到它出现
     （这正是「订单提交后 150 秒自动关闭」那条业务需要的能力：demo 列表页无任何自动刷新）
  (3) 负向：等一个**永不出现**的文本 + 短超时 -> **必须抛 AssertionError**，且信息里如实说明轮询了几轮
  (4) 负向自证：把超时设成极小 -> 快速失败（证明(1)不是"永远返回成功"那种恒真）

跑法（需要 demo 在 8000 上）：python tests/特性9-质量闸门体系/verify_wait_text.py
退出码：0 通过 · 1 有失败 · 2 环境不可用 · 3 内存不足 SKIP（**SKIP 不是通过**）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from framework.tools.common.text_io import force_stdio  # noqa: E402

force_stdio()

DEMO = os.environ.get("HYBRID_BASE_URL", "http://localhost:8000").rstrip("/")
MIN_MEM_MB = 550
NEVER = "这段文字永远不会出现-P22-等待验证"
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


def api(path: str, body=None, method: str = "POST", role: str = "order_admin"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(DEMO + path, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "X-Demo-Role": role})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except Exception as e:                                     # noqa: BLE001
        return -1, {"error": f"{type(e).__name__}: {e}"}


def load_harness():
    """渲染生成物侧的 harness（唯一实现）并 import —— 与用户跑生成的脚本时**同一份代码**。"""
    from framework.tools.generate import generator as G  # noqa: PLC0415
    tmp = Path("/tmp/p22_rendered_harness.py")
    tmp.write_text(G._render_harness(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("p22_rendered_harness", tmp)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


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

    H = load_harness()
    print(f"[harness] 已加载生成物侧实现：_assert_wait_text={callable(H._assert_wait_text)} · "
          f"_replay_last_search={callable(H._replay_last_search)}")
    check(callable(getattr(H, "_assert_wait_text", None)),
          "前置：生成物侧存在 _assert_wait_text（否则用户拿到的脚本根本用不了这个断言）")

    from playwright.sync_api import sync_playwright               # noqa: PLC0415
    from framework.tools.common.browser import launch_opts        # noqa: PLC0415

    created_name = f"P22等待验证-{int(time.time())}"
    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        pg = b.new_page()
        pg.goto(DEMO + "/orders.html?demo_role=order_admin", wait_until="domcontentloaded")
        pg.wait_for_selector("body[data-hybrid-ready='1']", timeout=8000)

        # ---- (1) 正向 A：已在页面上的文本 -> 探到就走 ----
        t0 = time.time()
        try:
            H._assert_wait_text(pg, "订单名称", timeout_ms=10000)
            dt = time.time() - t0
            check(dt < 3.0, "正向 A：目标已在页面上 -> 探到就走（不是白等满超时）", f"{dt:.2f}s")
        except Exception as e:                                 # noqa: BLE001
            check(False, "正向 A：等到已存在的文本", f"{type(e).__name__}: {str(e)[:80]}")

        # ---- (2) 正向 B：服务端新增 + refresh=research（列表页自己不刷新）----
        # 先在页面上点一次「搜索」——harness 的 _act 会记下"最近一次搜索"，research 靠它重放
        try:
            H._act(pg, "click", semantic="搜索",
                   primary=lambda page: page.get_by_role("button", name="搜索").first)
            pg.wait_for_timeout(300)
        except Exception as e:                                 # noqa: BLE001
            check(False, "前置：在页面上点一次「搜索」（供 research 重放）", f"{type(e).__name__}")
        st, d = api("/api/orders", {"name": created_name, "contract_no": "HT-1001", "bu": "bu_a",
                                    "mu": "0021", "file": "001", "order_type": "标准销售订单",
                                    "cust": "c1", "salesman": "s1"})
        check(st == 201, "前置：服务端确实新增了一条订单（页面还不知道）", f"HTTP {st} {d.get('no') or d.get('error')}")
        t0 = time.time()
        try:
            H._assert_wait_text(pg, created_name, timeout_ms=30000, refresh="research")
            check(True, "正向 B：refresh=research 每轮重放搜索 -> 等到服务端新增的记录", f"{time.time()-t0:.1f}s")
        except Exception as e:                                 # noqa: BLE001
            check(False, "正向 B：refresh=research 能等到（这是 150 秒自动关闭那条业务的地基）",
                  f"{type(e).__name__}: {str(e)[:90]}")

        # ---- (3) 负向：永不出现的文本 -> 必须抛 ----
        t0 = time.time()
        raised, msg = False, ""
        try:
            H._assert_wait_text(pg, NEVER, timeout_ms=3000, refresh="research")
        except AssertionError as e:
            raised, msg = True, str(e)
        except Exception as e:                                 # noqa: BLE001
            raised, msg = True, f"（非 AssertionError）{type(e).__name__}: {e}"
        check(raised and "轮询" in msg, "负向：永不出现的文本 -> 抛 AssertionError 且说明轮询轮数",
              f"{time.time()-t0:.1f}s · {msg[:70]}")
        check(raised and ("等待超时" in msg), "负向：失败信息里明确写「等待超时」（人看得懂为什么红）")

        # ---- (4) 负向自证：极小超时下"已存在的文本"也应该走完（证明不是恒真也不是恒假）----
        try:
            H._assert_wait_text(pg, "订单名称", timeout_ms=200)
            check(True, "自证：极小超时下，已在页面上的文本仍能命中（说明 (3) 的红是超时、不是实现坏了）")
        except Exception as e:                                 # noqa: BLE001
            check(False, "自证：极小超时下已在页面上的文本应能命中", f"{type(e).__name__}: {str(e)[:60]}")

        # ---- 收尾：撤掉造出来的那条（soft cancel -> 列表不再显示，保持零残渣）----
        api("/api/orders/cancel", {"no": d.get("no"), "reason": "信息输入错误"})
        st2, _ = api("/api/orders/cancel", {"no": d.get("no"), "reason": "信息输入错误"})
        print(f"[收尾] 已尝试撤掉 {d.get('no')}（软删；重复调用返回 HTTP {st2} 属正常）")
        pg.close()
        b.close()

    print()
    if fails:
        print(f"[NG] {len(fails)} 条判据不符预期：")
        for f in fails:
            print(f"   · {f}")
        return 1
    print("全部符合预期 [OK]（探到就走 · research 能等到新增记录 · 超时如实报 · 不恒真）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
