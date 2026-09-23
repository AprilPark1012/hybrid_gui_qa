"""订单系统页面 · 需求逐条端到端验证（2026-09-17 新增，AprilPark1012 的 6 条需求）。

跑法（需要 demo 在 8000 上：python -m demo.app）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python tests/featureTest/verify_order_pages.py        # 末行：全部符合预期 ✅ / 不符合预期 ❌

判据按需求编号一一对应（每条都真开浏览器点、真读页面状态，不看「代码里写了」）：
  ① 合同页有「查看订单」链接，点击**新开 tab**打开订单系统页面
  ② 订单列表默认 **3 页 × 20 条**（共 60 条）· 9 列字段与顺序一致 · 页码/上一页/下一页可用
  ③ 搜索：订单名称**全模糊** / 销售员**右模糊** / 客户**全模糊** / 业务单元·管理单元·帐套走「...」弹层
     —— 且这三类「...」弹层**没有「取消」按钮**（选中即回填并关闭）
  ④ 新建订单：必填校验（空提交不许创建）→ 全填提交 → 弹窗关闭 · 回到列表 · **第一行就是新订单**；
     「选择合同」弹层与业务单元同款（同样没有「取消」）
  ⑤ 点订单编号 / 订单名称 → **当前页**跳转到订单详情页；详情页按钮是「返回」，点击回订单列表
  ⑥ 点订单行的合同编号 → **新 tab** 打开该合同详情；该页按钮是「返回」，点击**关闭本 tab**

截图落在 output/order_shots/（output/ 不入库），用于人工确认页面长相。
"""
from __future__ import annotations

import json
import sys
import time
import traceback
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from framework.tools.common.text_io import force_stdio  # noqa: E402
from framework.tools.probe.scope_locate import scope_locate  # noqa: E402

force_stdio()


from framework.tools.probe.scope_locate import scope_locate  # noqa: E402


def _pick(page, modal, row_text):
    """在挑选弹层里点「含 row_text 的那一行」的按钮（P16 批 5）。

    为什么改成这样：行内埋点（`pick-*` 按钮 / `prow-*` 行）已按「真实系统只有**顶层容器**有埋点」
    的口径撤除 ⇒ 判据自己也必须走**顶层锚点 + 容器内下钻**，顺带把这条能力在真 demo 上跑一遍。
    行锚歧义（多行都含该文本）会在这里**如实失败**，绝不猜第一个。
    """
    r = scope_locate(page, {"kind": "dialog", "by": "test_id", "value": modal},
                     [{"axis": "row", "by": "text", "value": row_text},
                      {"axis": "target", "by": "role", "value": "button"}])
    if not r["ok"]:
        raise RuntimeError(f"下钻定位失败（modal={modal} 行锚={row_text!r}）：{r.get('reason')}")
    return r["locator_obj"]
DEMO = "http://localhost:8000"
SHOTS = BASE / "output" / "order_shots"
RESULTS: list[tuple[bool, str, str]] = []


def check(ok, desc, detail=""):
    RESULTS.append((bool(ok), desc, detail))
    print(f"  {('✅' if ok else '❌')} {desc}" + (f"  {detail}" if detail else ""))
    return bool(ok)


def _demo_up() -> bool:
    try:
        with urllib.request.urlopen(DEMO + "/api/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _api(path: str):
    with urllib.request.urlopen(DEMO + path, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def _reset():
    req = urllib.request.Request(DEMO + "/api/reset", data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def _shot(page, name: str):
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / name
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"     📸 {path}")
    except Exception as e:                        # 截图失败不该影响判据
        print(f"     ⚠️ 截图失败 {name}: {type(e).__name__}: {e}")


def _rows(page) -> list[str]:
    return page.eval_on_selector_all(
        "#tbody-orders tr", "els => els.map(e => e.innerText.replace(/\\s+/g,' ').trim())")


def _no_cancel(page, modal_testid: str) -> int:
    """需求③④：这些弹层里**不该有**「取消」按钮 —— 返回取消按钮个数。"""
    return page.locator(f"#{modal_testid} button", has_text="取消").count()


def _ready(page, timeout: int = 8000):
    page.wait_for_function("() => document.body.dataset.hybridReady === '1'", timeout=timeout)


def run() -> None:
    h = _api("/api/health")
    check(h.get("order_presets") == 60 and h.get("orders_per_page") == 20,
          "服务端声明订单数据口径（60 条 = 3 页 × 20）",
          f"order_presets={h.get('order_presets')} orders_per_page={h.get('orders_per_page')}")

    from playwright.sync_api import sync_playwright
    from framework.tools.common.browser import launch_opts

    _reset()
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_opts(headless=True))
        ctx = browser.new_context()
        page = ctx.new_page()

        # ============================ ① 入口 ============================
        print("\n===== ① 合同管理系统 → 「查看订单」→ 新 tab =====")
        page.goto(DEMO + "/", wait_until="networkidle")
        _ready(page)
        entry = page.locator("#link-orders")
        check(entry.count() == 1 and entry.inner_text().strip() == "查看订单",
              "合同页有「查看订单」链接且文案正确", f"count={entry.count()}")
        check(entry.get_attribute("target") == "_blank",
              "该链接 target=_blank（新 tab 打开）", f"target={entry.get_attribute('target')}")
        _shot(page, "01_contracts_entry.png")
        tabs_before = len(ctx.pages)
        with ctx.expect_page() as pinfo:
            entry.click()
        orders = pinfo.value
        orders.wait_for_load_state("networkidle")
        _ready(orders)
        check("/orders.html" in orders.url and len(ctx.pages) == tabs_before + 1,
              "点击后**新开了一个 tab**打开订单系统页面", f"url={orders.url.split('/')[-1]} tabs={len(ctx.pages)}")

        # ============================ ② 列表 + 分页 ============================
        print("\n===== ② 订单列表：3 页 × 20 条 · 9 列字段 =====")
        headers = orders.eval_on_selector_all(
            "#tbl-orders thead th", "els => els.map(e => e.innerText.trim())")
        want = ["订单编号", "合同编号", "订单名称", "管理单元", "销售员", "订单类型", "业务单元", "帐套", "客户"]
        check(headers == want, "9 列字段与顺序完全一致", f"{headers}")
        check(orders.locator("#total").inner_text().strip() == "60",
              "共 60 条订单（3 页 × 20）", f"total={orders.locator('#total').inner_text().strip()}")
        check(orders.locator("#page-info").inner_text().strip() == "第 1 / 3 页",
              "显示「第 1 / 3 页」", orders.locator("#page-info").inner_text().strip())
        r1 = _rows(orders)
        check(len(r1) == 20 and r1[0].startswith("SO-1001"),
              "第 1 页 20 行、首行 SO-1001", f"行数={len(r1)} 首行={r1[0][:16]}")
        _shot(orders, "02_orders_list_p1.png")
        # 分页按钮不再有行内埋点 ⇒ 走 pager 容器下钻（`data-page` 是页面自己的业务属性）
        orders.locator("#pager").locator("button[data-page='2']").click()
        orders.wait_for_function("() => document.getElementById('page-info').textContent.includes('2 / 3')", timeout=8000)
        r2 = _rows(orders)
        check(len(r2) == 20 and r2[0].startswith("SO-1021"),
              "点页码「2」⇒ 第 2 页 20 行、首行 SO-1021", f"行数={len(r2)} 首行={r2[0][:16]}")
        orders.locator("#btn-next-o").click()
        orders.wait_for_function("() => document.getElementById('page-info').textContent.includes('3 / 3')", timeout=8000)
        r3 = _rows(orders)
        check(len(r3) == 20 and r3[-1].startswith("SO-1060"),
              "「下一页」⇒ 第 3 页 20 行、末行 SO-1060", f"行数={len(r3)} 末行={r3[-1][:16]}")
        _shot(orders, "02b_orders_list_p3.png")
        orders.locator("#btn-prev-o").click()
        orders.wait_for_function("() => document.getElementById('page-info').textContent.includes('2 / 3')", timeout=8000)
        check(True, "「上一页」回第 2 页", orders.locator("#page-info").inner_text().strip())

        # ============================ ③ 搜索 ============================
        print("\n===== ③ 搜索：订单名称全模糊 / 销售员右模糊 / 客户全模糊 / 「...」弹层（无「取消」）=====")

        def search(patch: dict, expect_total: int, desc: str):
            orders.locator("#btn-reset-o").click()
            orders.wait_for_timeout(300)
            for tid, val in patch.items():
                orders.fill(f"#{tid}", val)
            orders.locator("#btn-search-o").click()
            orders.wait_for_function(
                f"() => document.getElementById('total').textContent.trim() === '{expect_total}'", timeout=8000)
            got = orders.locator("#total").inner_text().strip()
            check(got == str(expect_total), desc, f"命中 {got} 条（期望 {expect_total}）")

        search({"tb-o-name": "订单1"}, 11, "订单名称「订单1」= 全模糊（含订单10~订单19）⇒ 11 条")
        search({"tb-o-salesman": "张"}, 10, "销售员「张」= 右模糊（张伟 10 条；「伟」这种非前缀不命中见负向）")
        search({"tb-o-cust": "科技"}, 20, "客户「科技」= 全模糊（华信科技 10 + 中科智慧 10）⇒ 20 条")
        # 负向：右模糊 ≠ 全模糊
        orders.locator("#btn-reset-o").click()
        orders.wait_for_timeout(300)
        orders.fill("#tb-o-salesman", "伟")
        orders.locator("#btn-search-o").click()
        orders.wait_for_timeout(500)
        check(orders.locator("#total").inner_text().strip() == "0",
              "负向：销售员输入「伟」（包含但非前缀）⇒ 0 条（证明是右模糊而不是全模糊）",
              f"命中 {orders.locator('#total').inner_text().strip()} 条")

        for kind, btn, inp, val, label in [
            ("bu", "btn-pick-bu-search", "tb-o-bu", "bu_a", "业务单元"),
            ("mu", "btn-pick-mu-search", "tb-o-mu", "0451", "管理单元"),
            ("file", "btn-pick-file-search", "tb-o-file", "002", "帐套"),
        ]:
            orders.locator("#btn-reset-o").click()
            orders.wait_for_timeout(300)
            orders.locator(f"#{btn}").click()
            orders.wait_for_selector(f"#modal-pick-{kind}.show", timeout=5000)
            n_cancel = _no_cancel(orders, f"modal-pick-{kind}")
            if kind == "bu":
                _shot(orders, "03_pick_bu_modal.png")
            check(n_cancel == 0, f"{label}「...」弹层里**没有**「取消」按钮", f"取消按钮数={n_cancel}")
            # 行内「选择」按钮没有 id/testid（JS 逐行渲染）⇒ 走**弹层锚点 + 行锚文本 + 目标**下钻
            _r = scope_locate(orders, {"kind": "dialog", "by": "test_id", "value": f"modal-pick-{kind}"},
                              [{"axis": "row", "by": "text", "value": str(val)},
                               {"axis": "target", "by": "role", "value": "button"}])
            check(_r.get("ok"), f"{label}挑选层内「{val}」下钻定位成功", f"reason={_r.get('reason')}")
            _r["locator_obj"].click()
            orders.wait_for_timeout(300)
            filled = orders.input_value(f"#{inp}")
            still_open = orders.locator(f"#modal-pick-{kind}.show").count()
            check(filled == val and not still_open,
                  f"{label}选中「{val}」⇒ 回填输入框 + 弹层关闭", f"值={filled} 弹层还开着={bool(still_open)}")
            orders.locator("#btn-search-o").click()
            orders.wait_for_timeout(500)
            got = orders.locator("#total").inner_text().strip()
            check(got.isdigit() and got != "60", f"{label} 精确筛选生效（{val} ⇒ {got} 条）", f"命中 {got} 条")
            orders.locator("#btn-reset-o").click()
            orders.wait_for_timeout(300)

        # ============================ ④ 新建订单 ============================
        print("\n===== ④ 新建订单（必填校验 → 提交 → 第一行就是新订单）=====")
        orders.locator("#btn-new-order").click()
        orders.wait_for_selector("#modal-new-order.show", timeout=5000)
        orders.locator("#btn-submit-order").click()
        orders.wait_for_timeout(400)
        st = orders.locator("#status-o").inner_text().strip()
        check("请填写全部必填字段" in st, "空表单提交被拦（8 项必填）", f"提示：{st}")
        check(_api("/api/orders")["total"] == 60, "空提交没有创建任何订单（服务端仍 60 条）")

        name = f"订单冒烟_{time.strftime('%H%M%S')}"
        orders.fill("#o-name", name)
        orders.locator("#btn-pick-contract").click()
        orders.wait_for_selector("#modal-pick-contract.show", timeout=5000)
        n_cancel_c = _no_cancel(orders, "modal-pick-contract")
        check(n_cancel_c == 0, "「选择合同」弹层与业务单元同款：无「取消」按钮", f"取消按钮数={n_cancel_c}")
        _pick(orders, "modal-pick-contract", "HT-1005").click()
        orders.wait_for_timeout(250)
        check(orders.input_value("#o-contract") == "HT-1005",
              "选择合同 ⇒ 回填合同编号", orders.input_value("#o-contract"))
        for btn, modal, row_anchor, inp, expect in [
            ("btn-pick-bu", "modal-pick-bu", "bu_b", "o-bu", "bu_b"),
            ("btn-pick-mu", "modal-pick-mu", "1031", "o-mu", "1031"),
            ("btn-pick-file", "modal-pick-file", "003", "o-file", "003"),
        ]:
            orders.locator(f"#{btn}").click()
            orders.wait_for_timeout(250)
            _pick(orders, modal, row_anchor).click()
            orders.wait_for_timeout(250)
            got = orders.input_value(f"#{inp}")
            check(got == expect, f"弹层选择回填 {inp}", f"值={got}")
        orders.select_option("#o-type", "标准销售订单")
        orders.locator("#btn-pick-cust").click()
        orders.wait_for_timeout(250)
        _pick(orders, "modal-pick-cust", "上海远东贸易有限公司").click()
        orders.wait_for_timeout(250)
        orders.locator("#btn-pick-salesman").click()
        orders.wait_for_timeout(250)
        _pick(orders, "modal-pick-salesman", "王强").click()
        orders.wait_for_timeout(250)
        orders.fill("#o-remark", "需求④冒烟：备注选填")
        _shot(orders, "04_new_order_modal_filled.png")
        orders.locator("#btn-submit-order").click()
        orders.wait_for_function("() => document.getElementById('status-o').textContent.includes('已新增订单')",
                                 timeout=8000)
        check(not orders.locator("#modal-new-order.show").count(),
              "提交后新建弹窗关闭（回到订单列表）", orders.locator("#status-o").inner_text().strip())
        first = _rows(orders)[0]
        check(name in first, "列表**第一行**就是刚新建的订单", first[:80])
        check(_api("/api/orders")["total"] == 61, "服务端订单数 60 → 61")
        rec = _api("/api/orders?page=1")["items"][0]
        check(rec["name"] == name and rec["contract_no"] == "HT-1005" and rec["remark"] == "需求④冒烟：备注选填",
              "新建订单落库字段正确（含选填备注）",
              f"{rec['no']} 合同={rec['contract_no']} 客户={rec['custName']} 销售员={rec['salesmanName']} 备注={rec['remark']}")
        _shot(orders, "05_after_submit_first_row.png")
        new_no = rec["no"]

        # ============================ ⑤ 订单详情（当前页跳转） ============================
        print("\n===== ⑤ 点订单编号 / 订单名称 ⇒ 当前页跳订单详情 ⇒ 「返回」 =====")
        # P16 批 6（口径 C）：行内链接 `olink-*`/`nlink-*` 埋点已撤 ⇒ 改走**行锚 + 列字段 + 目标**下钻
        # （这正是生产里唯一可行的路：顶层表格当锚点，行按内容锚定，列按 data-field 取，目标按角色取）
        for col_field, desc in [("orderNo", "点订单编号"), ("orderName", "点订单名称")]:
            orders.goto(DEMO + "/orders.html", wait_until="networkidle")
            _ready(orders)
            tabs_before = len(ctx.pages)
            _r = scope_locate(orders, {"kind": "table", "by": "test_id", "value": "tbl-orders"},
                              [{"axis": "row", "by": "text", "value": new_no},
                               {"axis": "col", "by": "field", "value": col_field},
                               {"axis": "target", "by": "role", "value": "link"}])
            check(_r.get("ok"), f"{desc} ⇒ 行锚 + 列字段下钻定位成功",
                  f"reason={_r.get('reason')}")
            if not _r.get("ok"):
                continue
            _r["locator_obj"].first.click()
            orders.wait_for_load_state("networkidle")
            _ready(orders)
            check("/order_detail.html" in orders.url and f"no={new_no}" in orders.url
                  and len(ctx.pages) == tabs_before,
                  f"{desc} ⇒ **当前页**跳到订单详情（未开新 tab）", orders.url.split("/")[-1])
            if col_field == "orderNo":
                detail = orders.evaluate(
                    "() => { const d = id => document.getElementById(id).textContent.trim();"
                    " return {no: d('d-no'), name: d('d-name'), ct: d('d-contract'), sm: d('d-salesman'),"
                    " cu: d('d-cust'), tp: d('d-type'), rm: d('d-remark')}; }")
                check(detail["no"] == new_no and detail["name"] == name and detail["ct"] == "HT-1005"
                      and detail["sm"] == "王强" and detail["cu"] == "上海远东贸易有限公司"
                      and detail["tp"] == "标准销售订单" and detail["rm"] == "需求④冒烟：备注选填",
                      "订单详情字段与新建时完全一致（含客户/销售员/类型/备注）", f"{detail}")
                _shot(orders, "06_order_detail.png")
            back_text = orders.locator("#btn-back").inner_text().strip()
            check(back_text == "返回", f"{desc} 的详情页按钮文案是「返回」", f"文案={back_text}")
            orders.locator("#btn-back").click()
            orders.wait_for_load_state("networkidle")
            check("/orders.html" in orders.url, f"{desc} 点「返回」⇒ 回到订单列表", orders.url.split("/")[-1])

        # ============================ ⑥ 合同编号 → 新 tab + 关闭 ============================
        print("\n===== ⑥ 点合同编号 ⇒ 新 tab 合同详情 ⇒ 「返回」关闭该 tab =====")
        orders.goto(DEMO + "/orders.html", wait_until="networkidle")
        _ready(orders)
        row_contract = orders.eval_on_selector(
            "#tbody-orders tr:first-child td[data-field=contractNo] a", "e => e.innerText.trim()")
        tabs_before = len(ctx.pages)
        with ctx.expect_page() as cinfo:
            orders.eval_on_selector(
                "#tbody-orders tr:first-child td[data-field=contractNo] a", "e => e.click()")
        ctab = cinfo.value
        ctab.wait_for_load_state("networkidle")
        _ready(ctab)
        check("/contract_detail.html" in ctab.url and f"no={row_contract}" in ctab.url and "from=order" in ctab.url
              and len(ctx.pages) == tabs_before + 1,
              "点订单行的合同编号 ⇒ **新 tab** 打开该合同详情（带 from=order）", ctab.url.split("/")[-1])
        got_no = ctab.eval_on_selector("#d-no", "e => e.innerText.trim()")
        check(got_no == row_contract, "该 tab 展示的正是该行合同编号", f"{got_no} vs {row_contract}")
        ctxt = ctab.locator("#btn-back").inner_text().strip()
        check(ctxt == "返回", "该合同详情页按钮文案是「返回」", f"文案={ctxt}")
        _shot(ctab, "07_contract_from_order.png")
        try:
            ctab.locator("#btn-back").click()
        except Exception as e:                    # 点击瞬间 tab 就关了 ⇒ 这里也可能抛，不算失败
            print(f"     （点击后 tab 立即关闭：{type(e).__name__}）")
        orders.wait_for_timeout(800)              # ⚠️ 用**还活着**的订单页等待，别在已关闭的 page 上等
        check(ctab.is_closed(), "点「返回」⇒ 该 tab 被关闭（回到订单列表页）",
              f"is_closed={ctab.is_closed()} 当前 tab 数={len(ctx.pages)}")

        browser.close()


def main() -> int:
    if not _demo_up():
        print(f"❌ 被测 demo 不可达（{DEMO}）——先跑：python -m demo.app")
        return 2
    try:
        run()
    except Exception as e:
        traceback.print_exc()
        check(False, "验证脚本异常中断", f"{type(e).__name__}: {e}")
    bad = [d for ok, d, _ in RESULTS if not ok]
    print("\n===== 结论 =====")
    if RESULTS and not bad:
        print(f"全部符合预期 ✅（{len(RESULTS)} 条判据全过；截图见 {SHOTS}）")
        return 0
    print(f"不符合预期 ❌  共 {len(RESULTS)} 条判据，失败 {len(bad)} 条：")
    for d in bad:
        print(f"   · {d}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
