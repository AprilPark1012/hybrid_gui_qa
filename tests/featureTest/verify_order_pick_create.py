"""订单页 · 弹层两种选中方式 + 临时新建回填（2026-09-18 需求②③）端到端验证。

跑法（需要 demo 在 8000 上：python -m demo.app）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python tests/featureTest/verify_order_pick_create.py

判据（每条都真开浏览器点、真读页面与服务端状态，不看「代码里写了什么」）：
  需求② 两种选中方式：六类选择弹层里，**点行** 与 **点该行「选择」按钮** 都要能选中并回填
        （客户/销售员弹层有「取消」，其余四类没有 —— 点「取消」绝不能算作选中）
  需求③ 临时新建：客户/销售员弹层里的「+ 新建」→ **叠一层弹框** 填名提交 ⇒
        ① 落进服务端**主数据**（后续弹层里能看到、能被搜到）② **直接回填**订单表单字段
        ③ 两层弹框一起关 ④ 负向：空名/重名不许创建（前端要有可见提示）
  闭环：新建客户 + 新建销售员 → 回填 → 填完其余必填 → **提交订单成功**（列表第一行就是它）
  隔离：/api/reset 之后临时新建的客户/销售员要一并复位（否则会污染后续用例）

截图落在 output/order_shots/（output/ 不入库）。
"""
from __future__ import annotations

import json
import re
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from framework.tools.common.text_io import force_stdio  # noqa: E402

force_stdio()
DEMO = "http://localhost:8000"
SHOTS = BASE / "output" / "order_shots"
RESULTS: list[tuple[bool, str, str]] = []

# 弹层类型 → (打开它的按钮, 弹层 testid, 回填目标输入框, 没有「取消」的弹层集合)
PICKS = [
    ("bu", "#btn-pick-bu", "modal-pick-bu", "#o-bu"),
    ("mu", "#btn-pick-mu", "modal-pick-mu", "#o-mu"),
    ("file", "#btn-pick-file", "modal-pick-file", "#o-file"),
    ("contract", "#btn-pick-contract", "modal-pick-contract", "#o-contract"),
    ("cust", "#btn-pick-cust", "modal-pick-cust", "#o-cust"),
    ("salesman", "#btn-pick-salesman", "modal-pick-salesman", "#o-salesman"),
]
NO_CANCEL = {"bu", "mu", "file", "contract"}          # 需求③：这四类刻意没有「取消」


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


def _post(path: str, payload: dict) -> tuple[int, dict]:
    """直接打接口（用于与服务端状态对照，不经过页面）。"""
    req = urllib.request.Request(DEMO + path, data=json.dumps(payload).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body}


def _shot(page, name: str):
    SHOTS.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(SHOTS / name), full_page=True)
        print(f"     📸 {SHOTS / name}")
    except Exception as e:
        print(f"     ⚠️ 截图失败 {name}: {type(e).__name__}: {e}")


def _ready(page, timeout: int = 8000):
    page.wait_for_function("() => document.body.dataset.hybridReady === '1'", timeout=timeout)


def _vis(page, modal_testid: str) -> bool:
    return page.locator(f"#{modal_testid}").is_visible()


def _wait_status(page, text: str, status_id: str = "status-o", timeout: int = 6000):
    """等状态栏出现某段文本 —— 页面动作大多是 async，不等待就会读到上一步的旧文本。"""
    page.wait_for_function(
        "([i, t]) => document.getElementById(i).textContent.includes(t)",
        arg=[status_id, text], timeout=timeout)


def _hits(page, status_id: str = "status-o") -> int:
    m = re.search(r"命中 (\d+) 条", page.inner_text("#" + status_id))
    return int(m.group(1)) if m else -1


def _val(page, sel: str) -> str:
    """读输入框显示值 + 真正的取值（data-value）。"""
    return (page.input_value(sel) or "").strip()


def _dval(page, sel: str) -> str:
    return (page.get_attribute(sel, "data-value") or "").strip()


def run() -> None:
    h = _api("/api/health")
    check(h.get("cust_create") is True and h.get("salesman_create") is True,
          "服务端声明能力：弹层内可临时新建客户/销售员", f"cust_create={h.get('cust_create')}")

    from playwright.sync_api import sync_playwright
    from framework.tools.common.browser import launch_opts

    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts())
        ctx = b.new_context(viewport={"width": 1440, "height": 950})
        page = ctx.new_page()
        try:
            _reset()
            page.goto(DEMO + "/orders.html")
            _ready(page)
            page.click("#btn-new-order")
            check(page.locator("#modal-new-order").is_visible(), "新建订单弹窗已打开")
            _shot(page, "pc01_new_order.png")

            # ---------- 需求②：六类弹层 × 两种选中方式 ----------
            for kind, opener, modal, target in PICKS:
                # (a) 点「选择」按钮
                page.click(opener)
                if not check(_vis(page, modal), f"[{kind}] 弹层能打开"):
                    continue
                row = page.locator(f"#{modal} tbody tr").first
                row_txt = (row.inner_text() or "").replace("\n", " ").strip()
                btn = page.locator(f"#{modal} tbody tr").first.locator(
                    "button[data-pick-value]")
                want_v = btn.get_attribute("data-pick-value")
                want_l = btn.get_attribute("data-pick-label")
                btn.click()
                ok = (not _vis(page, modal)) and _dval(page, target) == want_v
                check(ok, f"[{kind}] 点行内「选择」按钮 → 选中并回填",
                      f"{row_txt[:26]} ⇒ value={_val(page, target)!r} data={_dval(page, target)!r}")

                # (b) 点整行（需求②的另一半）
                page.click(opener)
                page.locator(f"#{modal} tbody tr").nth(1).click()
                ok2 = (not _vis(page, modal))
                check(ok2, f"[{kind}] 点**整行** → 选中并关闭弹层",
                      f"输入框={_val(page, target)!r} data={_dval(page, target)!r}")

            _shot(page, "pc02_two_ways_filled.png")

            # ---------- 回归：两类有「取消」、四类没有；点「取消」不算选中 ----------
            for kind, opener, modal, target in PICKS:
                n = page.locator(f"#{modal} button", has_text="取消").count()
                if kind in NO_CANCEL:
                    check(n == 0, f"[{kind}] 弹层里**没有**「取消」（按需求设计）", f"count={n}")
                else:
                    check(n == 1, f"[{kind}] 弹层里有「取消」", f"count={n}")
            # 取消不该回填：先清空客户字段再点取消。
            # ⚠️ 只读框（readonly）不能用 page.fill 清空 —— Playwright 会以 "element is not editable"
            #    一直重试到超时（实测踩到）；这类框只能走 JS 设置。
            page.evaluate("() => { const e = document.getElementById('o-cust');"
                          " e.value = ''; e.dataset.value = ''; }")
            page.click("#btn-pick-cust")
            page.locator("#modal-pick-cust button", has_text="取消").click()
            check(_val(page, "#o-cust") == "" and _dval(page, "#o-cust") == "",
                  "点「取消」不算选中（客户字段仍为空）",
                  f"value={_val(page, '#o-cust')!r} data={_dval(page, '#o-cust')!r}")

            # ---------- 需求③：临时新建客户 → 落主数据 + 回填 ----------
            before = len(_api("/api/customers"))
            page.click("#btn-pick-cust")
            page.click("#btn-new-cust")
            check(_vis(page, "modal-create-cust") and _vis(page, "modal-pick-cust"),
                  "「+ 新建客户」在弹层之上**叠了一层**弹框（选择层仍在）")
            _shot(page, "pc03_create_layered.png")

            # 负向 1：空名不许创建
            page.click("#btn-create-cust-submit")
            page.wait_for_function(
                "() => document.getElementById('status-o').textContent.includes('不能为空')",
                timeout=5000)
            still = _vis(page, "modal-create-cust")
            n_after = len(_api("/api/customers"))
            check(still and n_after == before,
                  "空名提交：不关弹框、也不创建（前端给提示）",
                  f"弹框仍在={still} 服务端客户数 {before}→{n_after} 提示={page.inner_text('#status-o')[:24]!r}")

            # 正例：填名提交
            # ⚠️ 必须等「可观测的状态变化」再判定：Playwright 的 click **不会**等它触发的异步 fetch
            #   （不等就会读到「弹框还在 + 服务端还没写」的中间态 —— 实测就是这么假红了一次，
            #    而同一次 check 的 detail 读 DOM 时回填已经生效，前后自相矛盾才暴露出来）。
            page.fill("#nc-name", "验证客户甲")
            page.fill("#nc-addr", "验证地址1号")
            page.click("#btn-create-cust-submit")
            page.wait_for_function(
                "() => !document.getElementById('modal-create-cust').classList.contains('show')",
                timeout=5000)
            page.wait_for_function(
                "() => document.getElementById('status-o').textContent.includes('已新建')",
                timeout=5000)
            names = [c["name"] for c in _api("/api/customers")]
            ok = (not _vis(page, "modal-create-cust")) and (not _vis(page, "modal-pick-cust"))
            check(ok, "新建客户提交后：**两层弹框一起关掉**")
            check("验证客户甲" in names, "新建的客户**落进服务端主数据**",
                  f"服务端客户={names}")
            check(_val(page, "#o-cust") == "验证客户甲" and _dval(page, "#o-cust").startswith("c"),
                  "新建的客户**直接回填**到订单表单的客户字段",
                  f"value={_val(page, '#o-cust')!r} data={_dval(page, '#o-cust')!r}")
            _shot(page, "pc04_cust_filled.png")

            # 新建的这条要能在弹层里看到（说明前端主数据也刷新了）
            page.click("#btn-pick-cust")
            rows_n = page.locator("#modal-pick-cust tbody tr").count()
            has = page.locator("#modal-pick-cust tbody tr",
                               has_text="验证客户甲").count()
            check(rows_n == before + 1 and has == 1,
                  "重新打开客户弹层：新建那条**在列表里**且可选",
                  f"行数 {before}→{rows_n}")
            # 点新建那条（点行）→ 仍能正确回填
            page.locator("#modal-pick-cust tbody tr", has_text="验证客户甲").click()
            check(_val(page, "#o-cust") == "验证客户甲", "点新建那条行也能回填（两种方式对新数据同样有效）")
            page.click("#btn-pick-cust")

            # 负向 2：重名不许创建（前端要显示服务端的人话）
            page.click("#btn-new-cust")
            page.fill("#nc-name", "验证客户甲")
            page.click("#btn-create-cust-submit")
            page.wait_for_function(
                "() => document.getElementById('status-o').textContent.includes('已存在')",
                timeout=5000)
            msg = page.inner_text("#status-o")
            check(_vis(page, "modal-create-cust") and "已存在" in msg,
                  "重名提交：被拒（弹框仍在 + 提示「已存在」）", f"提示={msg[:30]!r}")
            check(len(_api("/api/customers")) == before + 1, "重名没有产生第二条记录")
            page.click("#btn-create-cust-cancel")
            page.click("#btn-pick-cust-cancel")

            # ---------- 需求③：临时新建销售员 ----------
            s_before = len(_api("/api/salesmen"))
            page.click("#btn-pick-salesman")
            page.click("#btn-new-salesman")
            check(_vis(page, "modal-create-salesman"), "「+ 新建销售员」叠层弹框已打开")
            page.fill("#ns-name", "验证销售员甲")
            page.click("#btn-create-salesman-submit")
            page.wait_for_function(
                "() => !document.getElementById('modal-create-salesman').classList.contains('show')",
                timeout=5000)
            page.wait_for_function(
                "() => document.getElementById('status-o').textContent.includes('已新建')",
                timeout=5000)
            s_names = [s["name"] for s in _api("/api/salesmen")]
            check("验证销售员甲" in s_names and len(s_names) == s_before + 1,
                  "新建销售员落进服务端主数据", f"服务端销售员={s_names}")
            check((not _vis(page, "modal-create-salesman")) and (not _vis(page, "modal-pick-salesman"))
                  and _val(page, "#o-salesman") == "验证销售员甲",
                  "新建销售员后：两层弹框关闭 + 回填到销售员字段",
                  f"value={_val(page, '#o-salesman')!r}")

            # ---------- 闭环：新建的客户/销售员 → 提交订单成功 ----------
            page.fill("#o-name", "验证订单甲")
            page.click("#btn-pick-contract")
            page.locator("#modal-pick-contract tbody tr").first.click()
            page.click("#btn-pick-bu")
            page.locator("#modal-pick-bu tbody tr").first.click()
            page.click("#btn-pick-mu")
            page.locator("#modal-pick-mu tbody tr").first.click()
            page.click("#btn-pick-file")
            page.locator("#modal-pick-file tbody tr").first.click()
            page.select_option("#o-type", "标准销售订单")
            page.click("#btn-submit-order")
            page.wait_for_function(
                "() => document.getElementById('status-o').textContent.includes('已新增订单')",
                timeout=8000)
            first_row = page.locator("#tbody-orders tr").first.inner_text().replace("\n", " ")
            check("验证订单甲" in first_row, "闭环：新建客户/销售员后直接提交订单成功，且列表第一行就是它",
                  first_row[:70])
            _shot(page, "pc05_order_created.png")

            # ---------- 需求②（补充一）：**搜索区**的「...」弹层同样支持两种选中 ----------
            # 搜索区与订单表单共用同一个弹层 DOM，只是回填目标不同 ⇒ 这里证明回填落到**搜索条件**上
            for kind, opener, modal, target in [
                ("bu", "#btn-pick-bu-search", "modal-pick-bu", "#tb-o-bu"),
                ("mu", "#btn-pick-mu-search", "modal-pick-mu", "#tb-o-mu"),
                ("file", "#btn-pick-file-search", "modal-pick-file", "#tb-o-file"),
            ]:
                page.click(opener)
                page.locator(f"#{modal} tbody tr").first.click()      # 点整行
                check(not _vis(page, modal) and _dval(page, target) != "",
                      f"[搜索区 {kind}] 点**整行** → 回填搜索条件并关闭弹层", f"{_val(page, target)!r}")
                page.click(opener)
                page.locator(f"#{modal} tbody tr").first.locator(
                    "button[data-pick-value]").click()                               # 点「选择」按钮
                check(not _vis(page, modal) and _dval(page, target) != "",
                      f"[搜索区 {kind}] 点行内「选择」按钮 → 同样回填搜索条件", f"{_val(page, target)!r}")
            # 用选出来的条件真搜一次，确认搜索链路仍通
            # ⚠️ doSearch 是 async（内部 await 取数）⇒ 点完必须等状态文本变化再判，
            #    否则读到的是上一步留下的旧文本（本脚本今天第三次栽在这个模式上）。
            page.click("#btn-search-o")
            page.wait_for_function(
                "() => document.getElementById('status-o').textContent.includes('搜索完成')",
                timeout=5000)
            check("搜索完成" in page.inner_text("#status-o"), "选出的筛选条件能正常执行搜索",
                  page.inner_text("#status-o")[:44])

            # ---------- 需求②（补充二）：**合同页**客户弹层的两种选中 ----------
            page.goto(DEMO + "/contracts.html")
            _ready(page)
            page.click("#btn-new")
            page.click("#btn-pick-c")
            page.locator("#modal-customer tbody tr").nth(1).click()        # 点整行
            check((not _vis(page, "modal-customer")) and _val(page, "#inp-c") != ""
                  and (page.get_attribute("#inp-c", "data-cust") or "") != "",
                  "[合同页] 点**整行** → 选中客户并回填新建表单",
                  f"value={_val(page, '#inp-c')!r} cust={page.get_attribute('#inp-c', 'data-cust')!r}")
            page.click("#btn-pick-c")
            page.locator("#modal-customer tbody tr").nth(2).locator(
                "button[data-pick]").click()                                              # 点「选择」按钮
            check((not _vis(page, "modal-customer")) and _val(page, "#inp-c") != "",
                  "[合同页] 点行内「选择」按钮 → 同样回填", f"value={_val(page, '#inp-c')!r}")

            # ---------- 需求②（补充三）：**合同页搜索区**的弹层（AprilPark1012 2026-09-18 追加） ----------
            # 语义约定：弹层**选中** ⇒ 精确命中该客户；手工输入 ⇒ 仍是右模糊（前缀）。
            page.goto(DEMO + "/contracts.html")
            _ready(page)
            page.click("#btn-pick-c-search")
            page.locator("#modal-customer tbody tr",
                         has_text="北京中科智慧科技").click()
            check((not _vis(page, "modal-customer"))
                  and (page.get_attribute("#tb-customer", "data-cust") or "") == "c5",
                  "[合同页搜索区] 点**整行**选中客户 → 回填 + 记住客户 id",
                  f"value={_val(page, '#tb-customer')!r} cust={page.get_attribute('#tb-customer', 'data-cust')!r}")
            page.click("#btn-search")
            _wait_status(page, "搜索完成", "status")
            n_exact = _hits(page, "status")
            check(n_exact == 3, "弹层选中 ⇒ **精确**命中该客户的合同（c5 共 3 条）", f"命中 {n_exact} 条")

            # 手输「北京」⇒ 右模糊：c1(4) + c5(3) 都命中 ⇒ 7 条（证明手输仍是右模糊、没被精确条件污染）
            page.fill("#tb-customer", "北京")
            page.click("#btn-search")
            _wait_status(page, "搜索完成", "status")
            n_fuzzy = _hits(page, "status")
            check(n_fuzzy == 7, "手输条件仍是**右模糊**（「北京」命中 c1+c5 共 7 条）", f"命中 {n_fuzzy} 条")
            # 既有语义不许被破坏：非前缀不命中
            page.fill("#tb-customer", "华信")
            page.click("#btn-search")
            _wait_status(page, "搜索完成", "status")
            n_none = _hits(page, "status")
            check(n_none == 0, "「华信」包含但不前缀 ⇒ 0 条（既有右模糊语义未被破坏）", f"命中 {n_none} 条")
            # 换一种选中方式：点行内「选择」按钮
            page.click("#btn-pick-c-search")
            page.locator("#modal-customer tbody tr").first.locator(
                "button[data-pick]").click()
            check((page.get_attribute("#tb-customer", "data-cust") or "") == "c1",
                  "[合同页搜索区] 点行内「选择」按钮 → 同样选中 c1",
                  f"cust={page.get_attribute('#tb-customer', 'data-cust')!r}")
            page.click("#btn-search")
            _wait_status(page, "搜索完成", "status")
            n_c1 = _hits(page, "status")
            check(n_c1 == 4, "按钮选中的客户同样走精确匹配（c1 共 4 条）", f"命中 {n_c1} 条")

            # ---------- 复位：临时新建的数据要一并清掉 ----------
            _reset()
            page.goto(DEMO + "/orders.html")
            _ready(page)
            c_n = len(_api("/api/customers"))
            s_n = len(_api("/api/salesmen"))
            check(c_n == 6 and s_n == 6,
                  "/api/reset 后临时新建的客户/销售员一并复位（不污染后续用例）",
                  f"客户={c_n} 销售员={s_n}")
            ent = page.locator("#modal-pick-cust tbody tr").count()
            check("验证客户甲" not in page.content(), "复位后页面里也不再有临时新建的记录")
            check(ent >= 0, "（信息）复位后客户弹层行数", f"rows={ent}")
        except Exception:
            check(False, "脚本执行中出现异常（下面是要点）", traceback.format_exc()[-600:])
        finally:
            ctx.close()
            b.close()

    ok_n = sum(1 for ok, _, _ in RESULTS if ok)
    bad = [(d, t) for ok, d, t in RESULTS if not ok]
    print(f"\n判据 {ok_n}/{len(RESULTS)} 通过")
    if bad:
        print("不符合预期的项：")
        for d, t in bad:
            print(f"  ❌ {d}  {t}")
        raise SystemExit(3)
    print("全部符合预期 ✅")
    raise SystemExit(0)


def main() -> int:
    if not _demo_up():
        print(f"⚠️ demo 不在 {DEMO} 上 ⇒ 先跑 `python -m demo.app`（本脚本不自起服务）")
        return 3
    print(f"=== 订单页弹层选中方式 + 临时新建回填 验证（目标 {DEMO}）===")
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
