"""弹层（picker）探测 · 端到端验证（2026-09-14 AprilPark1012需求①配套）。

为什么单独一个脚本、不叫 test_*.py：
  它要开真浏览器把 demo 的「新建合同 → 选择客户 → 客户列表层」走一遍，
  跟主用例套件（scripts/test_cases.py）跑在一起会抢内存、互相干扰
  （本机 1.87G / 无 swap，实测并发会招来 OOM killer）。

跑法（需要 demo 在 8000 上：python -m demo.app）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python tests/verify_picker_layer.py      # 期望最后一行：全部符合预期 ✅

判据（这条链的关键回归点）：
  ① explore/generate **共用**的 _try_collect_modal_items 必须探到弹层里的 6 个「选择」按钮，
     且语义名形如 选择@<客户名>（同名按钮只能靠所在行区分）；
  ② 探完弹窗/弹层必须关掉（页面恢复干净状态），否则下一页的探测是在「弹窗盖着」时做的；
  ③ 点开一层后的等待必须是**有界轮询**（不是固定 sleep）—— 有超时常量、且探到就走。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from framework.browser import launch_opts                  # noqa: E402
from framework.probe import probe_page                     # noqa: E402
from framework.explorer import (                           # noqa: E402
    _try_collect_modal_items, _LAYER_RENDER_WAIT_S, _LAYER_POLL_MS, _wait_fresh_items,
)
from playwright.sync_api import sync_playwright            # noqa: E402

DEMO = "http://localhost:8000"
EXPECT_PICK = {
    "选择@北京华信科技有限公司", "选择@上海远东贸易有限公司", "选择@广州南方物流有限公司",
    "选择@深圳前海数据服务有限公司", "选择@北京中科智慧科技有限公司", "选择@成都天府软件有限公司",
}

fails: list[str] = []


def check(ok: bool, desc: str, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {desc}{('  ' + detail) if detail else ''}")
    if not ok:
        fails.append(desc)


def main() -> int:
    # —— 一、静态判据：等待必须是有界的（回归「固定 sleep(300)」）——
    print("===== 一、等待策略必须是有界轮询（防复发：曾经的固定 sleep(300)）=====")
    src = (BASE / "framework" / "explorer.py").read_text(encoding="utf-8")
    check("_LAYER_RENDER_WAIT_S" in src and "_LAYER_POLL_MS" in src,
          "存在有界等待常量", f"({_LAYER_RENDER_WAIT_S}s / 每 {_LAYER_POLL_MS}ms 一轮)")
    check("_wait_fresh_items" in src, "点开一层走 _wait_fresh_items（轮询）")
    check(src.count("loc.first.click()\n        pg.wait_for_timeout(300)") == 0,
          "没有残留「点完固定 sleep(300) 就探测」的老写法")
    check("_page_alive" in src, "有页面存活判定（崩溃/OOM 不许伪装成「没有弹层」）")

    # 记 probe 调用次数：判定「有界轮询」靠的是**探测轮数**（确定性），
    # 而不是墙上时间 —— probe 本身要读几十个元素的属性，单次就要几秒，
    # 拿秒数当判据只会写出一条忽红忽绿的脆弱断言。
    import framework.probe as probe_mod
    _real_probe = probe_mod.probe_page
    calls: list[float] = []

    def counting_probe(*a, **kw):
        calls.append(time.monotonic())
        return _real_probe(*a, **kw)

    probe_mod.probe_page = counting_probe

    # —— 二、真浏览器走一遍 ——
    print("\n===== 二、真浏览器：新建合同 → 选择客户 弹层 =====")
    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        pg = b.new_context().new_page()
        pg.goto(DEMO)
        pg.wait_for_load_state("networkidle")
        base = probe_page(pg)
        check(len(base) > 0, "基础页探测非空", f"({len(base)} 个控件)")

        calls.clear()
        t0 = time.monotonic()
        layer = _try_collect_modal_items(pg, base)
        cost = time.monotonic() - t0
        probes_in_layer = len(calls)
        names = {it.get("semantic_name") for it in layer}
        got = EXPECT_PICK & names
        check(got == EXPECT_PICK, "弹层里 6 个「选择」按钮全部收集到（按所在行命名）",
              f"({len(got)}/{len(EXPECT_PICK)})")
        check(probes_in_layer <= 4, "探测轮数有界（没有反复空轮询把预算耗光）",
              f"(走完整个弹窗+弹层共 {probes_in_layer} 轮 probe，耗时 {cost:.1f}s — 单轮 probe 本身几秒)")
        # 弹窗/弹层必须被关掉：再探一次，弹层控件不该还在
        after = {it.get("semantic_name") for it in probe_page(pg)}
        check(not (EXPECT_PICK & after), "探完弹窗/弹层已被关掉（页面回到干净状态）")

        # 有界轮「探到就走」：健康页面上第一轮就该命中，不该等满 2.5s
        pg.get_by_role("button", name="新建合同").first.click()
        pg.wait_for_timeout(200)
        collected: list[dict] = []
        seen = set()

        def absorb(items):
            fresh = []
            for it in items:
                sn = it.get("semantic_name")
                if sn and sn not in seen:
                    seen.add(sn)
                    fresh.append(it)
                    collected.append(it)
            return fresh

        calls.clear()
        t0 = time.monotonic()
        _wait_fresh_items(pg, absorb)
        quick = time.monotonic() - t0
        check(collected and len(calls) == 1, "有界轮询：第一轮探到新控件就立刻返回（不等满超时）",
              f"(probe {len(calls)} 轮 / {quick:.2f}s，收集 {len(collected)} 个)")
        b.close()

    probe_mod.probe_page = _real_probe

    print("\n===== 结论 =====")
    if not fails:
        print("全部符合预期 ✅（弹层收集 6/6 + 探完关闭 + 有界轮询就绪）")
        return 0
    print(f"不符合预期 ❌  {fails}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
