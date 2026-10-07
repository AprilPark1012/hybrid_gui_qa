"""新建订单「三个区域」判据（需求㉒ · 2026-09-28 晚）

# HYBRID_DAILY_SKIP: V8.3 范围外 —— 断言绑 demo「新建订单」弹层旧区域结构（new-basic/new-more/new-lines，09-29 改版）。后续版本按新结构重写后恢复。
需求原文：
  「订单系统页面，点击"新建订单"按钮，弹出的订单页面，我发现还是老的订单页，你应该改成和订单详情页一样，
    分成3个区域，基础信息，更多信息和详细信息，这3个区域都允许编辑。页面底部有"保存"和"取消"按钮」

一段（HTTP + 静态，随时可跑）：服务端口径
  · POST /api/orders 带 more + lines ⇒ 201，且「更多信息」四项与订单行都落库（行号 1..N 重编）
  · 不传 more/lines 的旧调用 ⇒ 仍然 201（向后兼容：老脚本/老页面不受影响）
  · 行不合法（缺行类型/物料…）⇒ 400 且**整单回滚**（订单没被创建，绝不留半成品）
  · 基础必填缺失 ⇒ 400 且不落库
二段（浏览器，需 ≥550MB 内存，否则 SKIP exit 3）：
  · 点「新建订单」⇒ 弹层里有 3 个区域（基础信息 / 更多信息 / 详细信息）
  · 三个区域都是可编辑的（区域内的输入控件没有 disabled / readonly，locked 字段除外）
  · 底部按钮文案 = 「保存」「取消」；点保存 ⇒ 落库（更多信息 + 订单行都能在详情页看到）

运行：.venv/bin/python tests/featureTest/verify_new_order_3forms.py
退出码：0 全通过 · 1 有失败 · 3 内存不足跳过二段（**没跑 ≠ 通过**）
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))          # ⚠️ 不插这个，二段 import framework 会 ModuleNotFoundError

from framework.tools.common.text_io import force_stdio       # noqa: E402

force_stdio()          # 统一 UTF-8：Windows 控制台 cp936 下中文/✓ 会乱码（判据 test_utf8_io 守门）
DEMO = "http://localhost:8000"
ROLES = "order_admin"
fails: list[str] = []


def check(ok, desc, detail=""):
    print(("  ✅ " if ok else "  ❌ ") + desc + (f"   [{detail}]" if detail else ""))
    if not ok:
        fails.append(desc)


def call(method, path, body=None, roles=ROLES):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(DEMO + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Demo-Role": roles})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


BASIC = {"name": "三区域判据单", "contract_no": "HT-1001", "bu": "bu_a", "mu": "mu_a", "file": "F1",
         "order_type": "标准销售订单", "cust": "c1", "salesman": "s1"}
MORE = {"transport": "BY AIR", "creator": "小王", "carrier": "顺丰", "channel": "直销"}
LINES = [{"material": "M-1", "product": "P-1", "qty": "3", "unit": "个", "line_type": "产品订单行"},
         {"material": "M-2", "product": "P-2", "qty": "5", "unit": "件", "line_type": "服务订单行"}]


def part_http():
    print("\n===== 一段：服务端口径（更多信息 + 订单行一起落库）=====")
    call("POST", "/api/reset")
    st, before = call("GET", "/api/orders?page=1&size=1")
    total0 = before["total"]

    st, rec = call("POST", "/api/orders", {**BASIC, "more": MORE, "lines": LINES})
    check(st == 201, "正向：一条请求带「更多信息 + 订单行」⇒ 201", f"HTTP {st} {rec.get('no')}")
    no = rec.get("no")
    check(rec.get("saved") == 2, "回传 saved=2（两行都落库）", str(rec.get("saved")))
    st, det = call("GET", "/api/order?no=" + str(no))
    extra = det.get("extra") or {}
    check(extra == MORE, "更多信息四项落库（extra 与提交一致）", str(extra))
    st, ln = call("GET", "/api/order/lines?no=" + str(no))
    got = [(x["line_no"], x["material"], x["qty"], x["line_type"]) for x in ln["lines"]]
    check(got == [(1, "M-1", "3", "产品订单行"), (2, "M-2", "5", "服务订单行")],
          "订单行落库且行号 1..N 重编", str(got))
    check(det.get("created_by_label") == "订单管理员", "创建人按真账号记（需求㉑ 口径）", str(det.get("created_by_label")))

    st, page = call("GET", "/api/orders?page=1&size=1")
    check(st == 200 and page["total"] == total0 + 1, "订单总数 +1", f"{total0} → {page['total']}")

    st, rec2 = call("POST", "/api/orders", dict(BASIC, name="三区域判据单-旧调用"))
    check(st == 201 and not (rec2.get("extra")), "兼容：不传 more/lines 的旧调用仍 201（老脚本不受影响）", f"HTTP {st}")

    st, bad = call("POST", "/api/orders", {**BASIC, "name": "回滚验证单",
                                          "lines": [{"material": "M", "product": "P", "qty": "1"}]})
    check(st == 400 and "行" in (bad.get("error") or ""), "负向：行缺「行类型」⇒ 400", f"HTTP {st} {bad.get('error')}")
    st, page2 = call("GET", "/api/orders?page=1&size=200")
    check(not any(o["name"] == "回滚验证单" for o in page2["items"]),
          "负向：被拒的整单**已回滚**（不留「订单建了但行没落」的半成品）",
          f"总数 {page2['total']}")

    st, bad2 = call("POST", "/api/orders", {"name": "缺字段"})
    check(st == 400 and bad2.get("missing"), "负向：基础必填缺失 ⇒ 400 + missing", str(bad2.get("missing")))
    st, bad3 = call("POST", "/api/orders", dict(BASIC), roles="contract_admin")
    check(st == 403, "负向：非订单管理员建单 ⇒ 403（角色闸没被改坏）", f"HTTP {st}")
    call("POST", "/api/reset")


def part_static():
    print("\n===== 一段：页面结构（3 个区域 + 保存/取消 + 都可编辑）=====")
    h = (BASE / "demo" / "orders.html").read_text(encoding="utf-8")
    for tag, label in (("new-basic", "基础信息"), ("new-more", "更多信息"), ("new-lines", "详细信息")):
        ok = f'id="{tag}"' in h and f'data-testid="{tag}"' in h and label in h
        check(ok, f"弹层里有「{label}」区域（id={tag} + data-testid）")
    order = [h.index('id="new-basic"'), h.index('id="new-more"'), h.index('id="new-lines"')]
    check(order == sorted(order), "三个区域顺序 = 基础信息 → 更多信息 → 详细信息", str(order))
    check(">保存</button>" in h and "btn-submit-order" in h, "底部「保存」按钮（沿用 id btn-submit-order，老判据不断）")
    check(">取消</button>" in h and "btn-cancel-order" in h, "底部「取消」按钮（id btn-cancel-order）")
    check("newLines" in h and "btn-new-add-line" in h and "removeNewLine" in h,
          "详细信息区可增删订单行（新增行 / 删除）")
    check("moreFields" in h and all(k in h for k in ("o-transport", "o-creator", "o-carrier", "o-channel")),
          "更多信息四项齐全（运输方式/创建人/承运商/销售渠道）")
    # 「都能编辑」= 区域内没有把整块锁死的 disabled/readonly（locked 只针对订单编号这类）
    blk = h[h.index('id="new-basic"') - 200: h.index('id="new-lines"')]
    check("readonly" not in blk.replace('readonly autocomplete', ''), "基础/更多信息区没有整块 readonly 锁（可编辑）",
          "只有 pick 类选择框是 readonly 属性（点「...」选，属正常）")
    check(all(f"'{k}'" in h for k in ("o-name", "o-remark", "o-contract", "o-cust")),
          "原有字段 id 未改（o-name / o-remark / o-contract / o-cust 都在 fields 定义里）⇒ 老自动化仍能定位")
    check("btn-pick-contract" in h and "btn-pick-bu" in h and "btn-pick-cust" in h,
          "原有「...」选择按钮 id 未改（btn-pick-*）⇒ 弹层选择链路不受影响")


def part_browser():
    try:
        avail = int(next(l.split()[6] for l in open("/proc/meminfo", encoding="utf-8") if l.startswith("MemAvailable"))) // 1024
    except Exception:
        avail = 9999
    if avail < 550:
        print(f"\n⚠️ 二段（浏览器）SKIP：MemAvailable={avail}MB < 550MB 红线 ⇒ **没跑 ≠ 通过**")
        return 3
    from playwright.sync_api import sync_playwright
    from framework.tools.common.browser import launch_opts
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_opts(headless=True))
        pg = browser.new_context().new_page()
        pg.goto(DEMO + "/orders.html?demo_role=" + ROLES, wait_until="networkidle")
        pg.wait_for_function("() => document.body.dataset.hybridReady === '1'", timeout=8000)
        pg.click("#btn-new-order")
        pg.wait_for_selector("#modal-new-order", timeout=5000)
        for tid in ("new-basic", "new-more", "new-lines"):
            check(pg.locator(f'[data-testid="{tid}"]').count() == 1, f"弹层出现「{tid}」区域")
        check(pg.locator("#btn-submit-order").inner_text().strip() == "保存", "底部按钮文案 = 保存")
        check(pg.locator("#btn-cancel-order").inner_text().strip() == "取消", "底部按钮文案 = 取消")
        # 三个区域都可编辑
        dis = pg.eval_on_selector_all("#new-basic input, #new-more input, #new-basic select, #new-more select",
                                      "els => els.filter(e => e.disabled).length")
        ro = pg.eval_on_selector_all("#new-basic input:not([readonly]), #new-more input:not([readonly])",
                                     "els => els.length")
        check(dis == 0, "基础/更多信息区没有 disabled 控件（都可编辑）", f"disabled={dis}")
        check(ro > 0, "基础/更多信息区有可打字控件（可编辑）", f"可编辑={ro}")
        # 一行 = 3 个文本输入（物料/产品/数量）+ 2 个下拉（单位/行类型）
        check(pg.locator("#new-lines input").count() >= 3 and pg.locator("#new-lines select").count() >= 2,
              "详细信息区有行输入控件（可编辑）",
              f"input={pg.locator('#new-lines input').count()} select={pg.locator('#new-lines select').count()}")
        browser.close()
    return 0


if __name__ == "__main__":
    part_http()
    part_static()
    rc = part_browser()
    print("\n===== 结论 =====")
    if fails:
        print(f"不符合预期 ❌  失败 {len(fails)} 条：")
        for f in fails:
            print("   · " + f)
        sys.exit(1)
    print("全部通过 ✅" + (f"（二段 SKIP，退出码 {rc}）" if rc == 3 else ""))
    sys.exit(rc)
