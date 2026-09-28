"""需求⑪ · 开票前置校验 —— 只有「已关闭」的订单才能开票（正/负向端到端验证）。

为什么单独一个脚本、不叫 test_*.py：
  它验的是**被测 demo 的行为**（不是框架自己），而且分两层：
    ① 服务端权威闸：POST /api/invoices 带 from_order ⇒ 订单未关闭必须 400（纯 HTTP，秒级）
    ② 两道客户端闸（**需要真浏览器**）：订单页「去开票」按钮 / 开票页 ?from_order= 直链
  ② 要起浏览器 ⇒ 跟其余二类脚本同一口径：内存不够如实 SKIP（exit 3，**不是通过**）。

跑法（需要 demo 在 8000 上：python -m demo.app）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python tests/featureTest/verify_invoice_gate.py      # 期望最后一行：全部符合预期 ✅

判据（防假绿铁律）：**负向必须拦得住** ——
  · 未关闭的订单开票 ⇒ 必须 400 且**不落库**（发票数不变）
  · 已关闭的订单开票 ⇒ 必须 201 且发票记下 from_order（可追溯）
  · 客户端闸：未关闭 ⇒ 点「去开票」**不跳转**、只在 #status-o 提示；直链进门 ⇒ 禁「保存」
本脚本会 POST /api/reset 复原数据（跑完不留残渣）。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from framework.tools.common.text_io import force_stdio  # noqa: E402

force_stdio()

DEMO = os.environ.get("HYBRID_BASE_URL", "http://localhost:8000").rstrip("/")
MIN_MEM_MB = 550

fails: list[str] = []


def check(ok, desc, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + desc + (f"   [{detail}]" if detail else ""))
    if not ok:
        fails.append(desc)


def mem_available_mb() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return -1


# 需求⑮：本脚本跨两个角色 —— 关订单行/存行 = 订单管理员；创建发票 = 发票管理员
TEST_ROLES = os.environ.get("DEMO_TEST_ROLES", "order_admin,invoice_admin")


def _api(method: str, path: str, body=None, role: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"Content-Type": "application/json", "X-Demo-Role": role or TEST_ROLES}
    req = urllib.request.Request(DEMO + path, data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _dict(kind: str) -> str:
    return _api("GET", f"/api/dict?kind={kind}")[1]["values"][0]


def _invoice_count() -> int:
    d = _api("GET", "/api/invoices")[1]
    return len(d if isinstance(d, list) else d.get("items") or [])


def _mark_closed(no: str) -> str:
    """把某订单搞成「已关闭」：先存一行，再关闭全部行（需求⑧ 手工关单）。"""
    _api("POST", "/api/order/lines", {"no": no, "lines": [
        {"material": "M-1", "product": "P-1", "qty": "2", "unit": "个", "line_type": "产品订单行"}]})
    return _api("POST", "/api/order/lines/close", {"no": no})[1].get("order_status")


def _invoice_body(from_order=None) -> dict:
    b = {"bu": _dict("bu"), "invoice_type": _dict("invoice_type"), "invoice_date": "2026-09-28",
         "salesman": _api("GET", "/api/salesmen")[1][0]["id"], "currency": _dict("currency"),
         "cust": _api("GET", "/api/customers")[1][0]["id"],
         "lines": [{"period": "1", "line_type": "物料行", "qty": "10", "unit": "个"}]}
    if from_order:
        b["from_order"] = from_order
    return b


def main() -> int:
    try:
        _, h = _api("GET", "/api/health")
    except Exception as e:                                   # noqa: BLE001
        print(f"❌ 被测 demo 不可达（{DEMO}）——先跑：python -m demo.app  [{e}]")
        return 2

    # ===================== 一、静态 + 服务端权威闸（不需要浏览器） =====================
    print("===== 一、服务端权威闸（纯 HTTP）=====")
    _api("POST", "/api/reset")
    check(h.get("invoice_requires_closed") is True,
          "/api/health 声明开票前置条件（invoice_requires_closed）", str(h.get("invoice_requires_closed")))
    check(h.get("closed_state") == "已关闭",
          "closed_state 口径来自服务端（页面不写死）", str(h.get("closed_state")))

    orders_html = (BASE / "demo" / "orders.html").read_text(encoding="utf-8")
    create_html = (BASE / "demo" / "invoice_create.html").read_text(encoding="utf-8")
    check("closedState" in orders_html and "goInvoice" in orders_html,
          "订单页「去开票」按服务端口径取 closed_state", "orders.html")
    check("orderBlocked" in create_html and ':disabled="orderBlocked"' in create_html,
          "开票页直链也会拦（禁用「保存」）", "invoice_create.html")

    before = _invoice_count()
    st, d = _api("POST", "/api/invoices", _invoice_body("SO-1001"))       # 预置订单=已新建
    check(st == 400 and "只有「已关闭」的订单才能开票" in d.get("error", ""),
          "负向：未关闭的订单开票被拒（HTTP 400 + 文案）", f"HTTP {st} {d.get('error')}")
    check(d.get("order_status") == "已新建", "响应带 order_status（前端可展示拦截原因）",
          str(d.get("order_status")))
    check(_invoice_count() == before, "负向：被拒的开票**没有落库**",
          f"发票数 {before} → {_invoice_count()}")

    st, d = _api("POST", "/api/invoices", _invoice_body("SO-9999"))
    check(st == 404 and "未找到来源订单" in d.get("error", ""),
          "负向：来源订单不存在 ⇒ 404", f"HTTP {st} {d.get('error')}")

    st, d = _api("POST", "/api/invoices", _invoice_body())                # 不带 from_order
    check(st == 201, "回归：不带 from_order 的普通开票不受影响（防误伤老流程）",
          f"HTTP {st} no={d.get('no')}")

    st = _mark_closed("SO-1005")
    check(st == "已关闭", "前置：把 SO-1005 关成「已关闭」（存行 → 关全部行）", str(st))
    st, d = _api("POST", "/api/invoices", _invoice_body("SO-1005"))
    check(st == 201 and d.get("from_order") == "SO-1005",
          "正向：已关闭的订单放行开票（并记下来源订单）",
          f"HTTP {st} no={d.get('no')} from_order={d.get('from_order')}")
    _api("POST", "/api/reset")

    # ===================== 二、两道客户端闸（真浏览器） =====================
    print("\n===== 二、客户端闸（真浏览器：按钮不跳转 / 直链禁保存）=====")
    mem = mem_available_mb()
    print(f"[内存] MemAvailable = {mem} MB（跑浏览器需要 ≥{MIN_MEM_MB} MB）")
    if mem < MIN_MEM_MB:
        print("SKIP：内存不够，未跑浏览器判据（如实跳过，不报假绿）→ exit 3")
        # ⚠️ 但**一段已跑出来的失败绝不能被 SKIP 吞掉**（否则 SKIP 变成假绿）
        if fails:
            print(f"\n❌ 上面已有一段的 {len(fails)} 条判据不符预期（这些与内存无关，必须修）：")
            for x in fails:
                print(f"   · {x}")
            return 1
        print("\n（服务端权威闸部分已跑完）")
        return 3

    from playwright.sync_api import sync_playwright            # noqa: PLC0415
    from framework.tools.common.browser import launch_opts      # noqa: PLC0415

    def _ready(page, timeout=8000):
        page.wait_for_function("() => document.body.dataset.hybridReady === '1'", timeout=timeout)

    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        ctx = b.new_context()
        page = ctx.new_page()

        # ① 未关闭 ⇒ 点「去开票」不跳转、只提示
        page.goto(DEMO + "/orders.html?demo_role=" + TEST_ROLES.split(",")[0], wait_until="networkidle")
        _ready(page)
        page.check("#rd-SO-1001")
        page.click("#btn-to-invoice")
        page.wait_for_timeout(300)
        url, st_text = page.url, page.locator("#status-o").inner_text().strip()
        check("/orders.html" in url, "负向：未关闭的订单点「去开票」**不跳转**", url.split("/")[-1])
        check("只有「已关闭」的订单才能开票" in st_text, "负向：状态行给出拦截原因", st_text)

        # ② 关成已关闭 ⇒ 同一动作放行（同一页面、同一按钮，排除「按钮坏了」的假绿）
        _mark_closed("SO-1001")
        page.goto(DEMO + "/orders.html?demo_role=" + TEST_ROLES.split(",")[0], wait_until="networkidle")
        _ready(page)
        page.check("#rd-SO-1001")
        page.click("#btn-to-invoice")                       # 本页跳转（location.href），不是新 tab
        page.wait_for_url("**/invoice_create.html*", timeout=8000)
        _ready(page)
        check("from_order=SO-1001" in page.url, "正向：已关闭 ⇒ 跳到开票页并带来源订单",
              page.url.split("/")[-1])
        check(page.locator("#btn-inv-submit").is_enabled(),
              "正向：开票页「保存」可用（未被误拦）")
        check(page.locator("#i-bu").input_value() != "", "正向：业务单元已自动带入",
              page.locator("#i-bu").input_value())
        page.close()

        # ③ 直链进未关闭的订单 ⇒ 禁保存
        n_before = _invoice_count()
        p2 = ctx.new_page()
        p2.goto(DEMO + "/invoice_create.html?from_order=SO-1002&demo_role=" + TEST_ROLES, wait_until="networkidle")
        _ready(p2)
        txt = p2.locator("#inv-status").inner_text().strip()
        check(p2.locator("#btn-inv-submit").is_disabled(),
              "负向：直链进未关闭的订单 ⇒ 「保存」被禁用")
        check("只有「已关闭」的订单才能开票" in txt, "负向：直链拦截给出原因", txt)
        check(n_before == _invoice_count(), "负向：直链也没法落库（发票数不变）")
        p2.close()
        b.close()

    _api("POST", "/api/reset")
    print()
    if fails:
        print(f"❌ {len(fails)} 条判据不符预期：")
        for f in fails:
            print(f"   · {f}")
        return 1
    print("全部符合预期 ✅（服务端拦得住、客户端两道闸也对、已关闭的正常放行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
