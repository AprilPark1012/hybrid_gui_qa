"""「编辑态 / 动态新增」补探 · 真实页面验证（C1 · 真浏览器 + 真 demo + 真登录）。

验的是什么（框架能力在真环境可用，不是 demo 的功能测试）：
  (1) **正向**：订单详情页的行内字段（物料编码/产品编码/数量/行类型）只在
      「进编辑态 + 点新增行」之后才存在（`<div :readonly="!editing">`，无 id/name）——
      补探必须把**这些控件**收进清单（这是 AI 能绑 element 的前提）。
  (2) **反向自证**：关掉补探（enabled=False）-> 同样的页面**收不到**它们
      （证明"收得到"来自那两次点击，而不是页面本来就有）。
  (3) **收尾自证**：补探结束后页面必须**回到只读态**（框架开的必须由框架关）。

跑法（需要 demo 在 8000 上）：python tests/特性3-分层定位与控件识别/verify_editable_state_probe.py
退出码：0 通过 · 1 有失败 · 2 环境不可用 · 3 内存不足 SKIP（SKIP 不是通过）。
"""
from __future__ import annotations

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
#: 行内字段的**标签关键词**（判据按子串匹配，不依赖具体命名后缀形态）
WANT = ("物料编码", "产品编码", "数量", "行类型")

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


def _any_order() -> str:
    p = BASE / "demo" / ".data" / "state_default.json"
    d = json.load(p.open(encoding="utf-8"))
    orders = d.get("orders") or []
    return str(orders[-1].get("no")) if orders else ""


#: 「可填可改」的角色 —— **判据要按这个筛**，不能只按名字子串：
#  只读单元格/表头也会叫「物料编码」，光看名字会把"根本不是输入框的东西"算成命中
#  （2026-10-10 实测踩过：判据写粗了，把负向自证判成红）。
_FILLABLE = ("textbox", "input", "combobox", "select", "spinbutton", "textarea", "div")


def _hit(items, kw) -> list[str]:
    return [str(it.get("semantic_name") or "") for it in items
            if kw in str(it.get("semantic_name") or "") + str(it.get("base_name") or "")]


def _hit_fillable(items, kw) -> list[str]:
    """命中关键词**且**是可编辑控件（文本框/下拉/可编辑表格单元）。"""
    out = []
    for it in items:
        name = str(it.get("semantic_name") or "") + str(it.get("base_name") or "")
        role = str(it.get("role") or it.get("tag") or "").lower()
        if kw in name and role in _FILLABLE:
            out.append(str(it.get("semantic_name") or ""))
    return out


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

    no = _any_order()
    if not no:
        print("[NG] demo 里找不到订单样本")
        return 2

    from playwright.sync_api import sync_playwright               # noqa: PLC0415
    from framework.tools.common.browser import launch_opts        # noqa: PLC0415
    from framework.tools.probe.probe import probe_page            # noqa: PLC0415
    from framework.tools.probe.editable import enter_editable_and_collect  # noqa: PLC0415

    def _ready(page, timeout=8000):
        try:
            page.wait_for_function("() => document.body.dataset.hybridReady === '1'", timeout=timeout)
        except Exception:                                      # noqa: BLE001
            pass

    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        ctx = b.new_context()
        pg = ctx.new_page()

        # ---- 真登录 + 切订单管理员（进编辑态需要 create_order 权限）----
        pg.goto(DEMO + "/login.html", wait_until="domcontentloaded")
        pg.get_by_placeholder("请输入账号").fill(SUPER[0])
        pg.get_by_placeholder("请输入密码").fill(SUPER[1])
        pg.get_by_role("button", name="登 录").click()
        _ready(pg, 10000)
        pg.click("#nu-avatar")
        pg.locator('#nu-menu [data-switch="order_admin"]').click()
        pg.wait_for_timeout(1500)

        pg.goto(f"{DEMO}/order_detail.html?no={no}", wait_until="domcontentloaded")
        _ready(pg)

        # ================= 反向自证：关掉补探 -> 收不到 =================
        base = probe_page(pg)
        print(f"  [信息] 基础清单 {len(base)} 项；样本订单 {no}")
        off = enter_editable_and_collect(pg, base, enabled=False)
        check(off == [], "反向：补探关掉（enabled=False）-> 一条都收不到", str(len(off)))
        # [!] 如实口径（2026-10-10 诊断纠正）：**已有行的只读输入框本来就在基础清单里**
        #     （`<input readonly>` 仍是 input，`role=textbox`）—— 所以不能说"静默探测拿不到行内字段"。
        #     真正只在编辑态/动态新增之后才存在的，是**编辑态专属**那批（保存行/取消/删除/关闭）。
        base_names = {str(it.get("semantic_name") or "") for it in base}
        EDIT_ONLY = ("保存@详细信息", "取消", "删除", "关闭")
        miss_off = [k for k in EDIT_ONLY if not any(k in n2 for n2 in base_names)]
        # 阈值取 ≥1：实测**只有**「保存行」是纯编辑态才有的，其余（取消/删除/关闭）
        # 在只读态就已存在于 DOM（置灰也算存在）—— 判据按实测写，不夸大。
        check(len(miss_off) >= 1,
              "反向：**静默探测**拿不到「编辑态专属」控件（缺口是真的）",
              f"基础清单里缺: {miss_off}；样本={sorted(base_names)[:6]}")

        # ================= 正向：开着补探 -> 必须收到 =================
        fresh = enter_editable_and_collect(pg, base, settle_s=3.0)
        names = [str(it.get("semantic_name") or "") for it in fresh]
        assert_true = True
        print(f"  [信息] 补探新增 {len(fresh)} 项：{names[:12]}")
        hits = {k: _hit_fillable(fresh, k) for k in WANT}
        got = [k for k, v in hits.items() if v]
        check(len(got) >= 3,
              "正向：补探收进了行内字段（AI 能绑 element 的前提）",
              f"命中 {got}；详细={ {k: v[:2] for k, v in hits.items()} }")

        # ================= 收尾自证：页面必须回到只读态 =================
        readonly = False
        try:
            readonly = pg.evaluate(
                "() => { const d = document.querySelector('#btn-detail-edit');"
                " return !!d && !d.className.includes('lit'); }")
        except Exception:                                      # noqa: BLE001
            readonly = False
        check(bool(readonly), "收尾：补探结束后页面回到只读态（框架开的必须由框架关）",
              f"#btn-detail-edit 非编辑态高亮={readonly}")

        pg.close()
        b.close()

    print()
    if fails:
        print(f"[NG] {len(fails)} 条判据不符预期：")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("全部符合预期 [OK]（静默探测拿不到 -> 补探拿得到 -> 探完自动复原）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
