"""需求⑫ · 订单详情「编辑 / 保存 / 提交」闭环 + 合同编号找回 —— 正/负向端到端验证。

需求口径（他 2026-09-28 晚口述）：
  点「编辑」⇒ ① 本行「取消」**消失** ② 同一个按钮文案变「保存」（保存 = 表单1 + 表单2 + 表单3）
  ③ 「提交」按钮不变；**点「提交」前校验页面编辑是否已保存**，未保存 ⇒ 只提示、不提交。
另：合同编号 `#d-contract` 恢复为「容器（textContent = 合同编号）+ 新 tab 打开合同详情（带 from=order）」。

跑法（需要 demo 在 8000 上：python -m demo.app）：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python tests/featureTest/verify_order_detail_edit.py      # 期望最后一行：全部符合预期 ✅

分层：
  一、服务端落库闸（纯 HTTP，秒级）：POST /api/order/update —— 改字段/表2 生效、只读字段被忽略、
      必填不许清空（400 且**不落库**）、订单不存在 404。
  二、客户端按钮闭环（**真浏览器**，内存 <550MB ⇒ 如实 SKIP exit 3，**不是通过**）。
本脚本会 POST /api/reset 复原（跑完不留残渣）。
"""
from __future__ import annotations

import json
import os
import re
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
ORDER = "SO-1001"
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


# 需求⑮：写接口要角色权限 —— 自动化用**测试专用**角色头（页面上没有这个入口）
TEST_ROLE = os.environ.get("DEMO_TEST_ROLE", "order_admin")


def _api(method: str, path: str, body=None, role: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"Content-Type": "application/json"}
    if role is not False:
        hdr["X-Demo-Role"] = role or TEST_ROLE
    req = urllib.request.Request(DEMO + path, data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _order(no: str = ORDER) -> dict:
    return _api("GET", "/api/order?no=" + no)[1]


def _col_count(html: str) -> int:
    """网格列数（取 CSS grid-template-columns 的值个数）。"""
    m = re.search(r"\.lines-grid \{ display: grid; grid-template-columns: ([^;]+);", html)
    return len(m.group(1).split()) if m else -1


def order_html_cols(html: str) -> str:
    """表头 head 个数 vs 每行 cell 个数（错位会在这里露出来）。"""
    heads = len(re.findall(r'<div class="head"', html))
    cells = len(re.findall(r'<div class="cell"', html))
    return f"表头 head={heads}（含全选）/ 行内 cell 模板={cells} / CSS 列数={_col_count(html)}"


def main() -> int:
    try:
        _, h = _api("GET", "/api/health")
    except Exception as e:                                   # noqa: BLE001
        print(f"❌ 被测 demo 不可达（{DEMO}）——先跑：python -m demo.app  [{e}]")
        return 2

    # ===================== 一、服务端（纯 HTTP） =====================
    print("===== 一、服务端：POST /api/order/update（保存表单1 + 表单2）=====")
    _api("POST", "/api/reset")
    check(h.get("order_update") is True,
          "/api/health 声明订单可保存接口（order_update）", str(h.get("order_update")))

    want_fields = {"name": "验证订单甲", "order_type": "退货订单", "bu": "bu_c", "mu": "0451", "file": "002"}
    want_more = {"transport": "BY SEA 海运", "creator": "验证人", "carrier": "验证承运", "channel": "电商"}
    st, d = _api("POST", "/api/order/update", {"no": ORDER, "fields": want_fields, "more": want_more})
    upd = d                                     # 保存接口的回传（页面直接渲染它）
    check(st == 200, "正向：保存订单字段 + 表单2 四项", f"HTTP {st}")
    got = _order()
    check(all(got.get(k) == v for k, v in want_fields.items()),
          "正向：表单1 字段已落库", f"{ {k: got.get(k) for k in want_fields} }")
    check(all((got.get("extra") or {}).get(k) == v for k, v in want_more.items()),
          "正向：表单2 四项已落库（extra）", f"{got.get('extra')}")
    check("custName" in upd and "salesmanName" in upd and upd.get("order_status"),
          "正向：保存接口回传拼好名字与 order_status（页面可直接渲染）",
          f"cust={upd.get('custName')} 状态={upd.get('order_status')}")

    # 负向 1：必填不许被清空 ⇒ 400 且不落库
    st, d = _api("POST", "/api/order/update", {"no": ORDER, "fields": {"name": ""}})
    check(st == 400 and "name" in (d.get("missing") or []),
          "负向：把必填清空 ⇒ 400 + missing 指名", f"HTTP {st} {d.get('error')} missing={d.get('missing')}")
    check(_order().get("name") == "验证订单甲", "负向：被拒的保存**没有落库**（名称仍是上一次的值）",
          str(_order().get("name")))

    # 负向 2：订单不存在
    st, d = _api("POST", "/api/order/update", {"no": "SO-9999", "fields": {"name": "x"}})
    check(st == 404 and "未找到该订单" in d.get("error", ""), "负向：订单不存在 ⇒ 404",
          f"HTTP {st} {d.get('error')}")

    # 只读字段（页面 locked）：传了必须被忽略
    st, _ = _api("POST", "/api/order/update", {"no": ORDER, "fields": {
        "no": "SO-9999", "contract_no": "HT-9999", "salesman": "s9", "cust": "c9", "name": "只读字段测试"}})
    chk = _order()
    check(st == 200 and chk.get("no") == ORDER and chk.get("contract_no") == "HT-1001"
          and chk.get("salesman") == "s1" and chk.get("cust") == "c1" and chk.get("name") == "只读字段测试",
          "只读字段（编号/合同/销售员/客户）传了也被忽略，可改字段照常生效",
          f"no={chk.get('no')} 合同={chk.get('contract_no')} 名称={chk.get('name')}")

    # 静态：页面把闭环写全了（按钮/校验/合同链接）
    html = (BASE / "demo" / "order_detail.html").read_text(encoding="utf-8")
    app_py = (BASE / "demo" / "app.py").read_text(encoding="utf-8")
    check("onEditOrSave" in html and "{{ editing ? '保存' : '编辑' }}" in html,
          "页面：编辑/保存 同一个按钮 + 文案切换", "order_detail.html")
    check('v-if="!editing" id="btn-detail-cancel"' in html,
          "页面：编辑态下「取消」按钮消失", "order_detail.html")
    check("if (this.dirty)" in html and "请先点「保存」再提交" in html,
          "页面：提交前校验 dirty 并给提示", "order_detail.html")
    check("'/api/order/update'" in html and "/api/order/lines" in html,
          "页面：保存 = 表单1+2（update）+ 表单3（lines）两次调用", "order_detail.html")
    check("class=\"contract-link\"" in html and "&from=order" in html and "target=\"_blank\"" in html,
          "找回：合同编号 = 容器 + 新 tab 打开合同详情（带 from=order）", "order_detail.html")
    check("def update_order(" in app_py and 'path == "/api/order/update"' in app_py,
          "服务端：update_order + 路由都在", "app.py")

    # 需求⑬：表单3 四个按钮的只读态（新增行/保存/取消 置灰；全部关闭一直高亮）
    def _btn(tag_id: str) -> str:
        m = re.search(r'<button id="%s".*?>' % tag_id, html, re.S)
        return m.group(0) if m else ""

    for bid in ("btn-add-line", "btn-save-lines", "btn-cancel-lines"):
        b = _btn(bid)
        check(':disabled="!editing' in b and ':class="{ lit: editing }"' in b,
              f"需求⑬：#{bid} 只读态置灰 + 编辑态高亮（disabled 含 !editing、lit 绑 editing）",
              b[:60].replace("\n", " "))
    close_btn = _btn("btn-close-lines")            # 需求⑭ 起 id 改名（原来叫 btn-close-all-lines）
    check(close_btn != "" and "!editing" not in close_btn and "canOrder" in close_btn,
          "需求⑬/⑭/⑮：#btn-close-lines **不受编辑态限制**，只由角色决定（:disabled=\"!canOrder\"）",
          close_btn[:60])
    check(".lines-toolbar .btn:disabled" in html and ".lines-toolbar .btn.lit" in html,
          "需求⑬：置灰/高亮 CSS 都在（视觉上确实会变灰，不是只加属性）", "order_detail.html")

    # 需求⑭：「全部关闭」→「关闭」，关的是勾选的行（表头可全选）
    check('id="btn-close-lines"' in html and '>关闭</button>' in html
          and '<button id="btn-close-all-lines"' not in html,
          "需求⑭：按钮改名「全部关闭」→「关闭」，且**旧 id 无实际元素残留**"
          "（注释里保留改名记录不算残留）", _btn("btn-close-lines")[:60])
    check('id="chk-all-lines"' in html and 'class="ln-pick"' in html,
          "需求⑭：行首勾选列 + 表头全选勾选框都在", order_html_cols(html))
    check("toggleAllLines" in html and "closePicked" in html and "请先勾选要关闭的订单行" in html,
          "需求⑭：全选/关闭逻辑 + 未勾选时的提示都在")
    check(_col_count(html) == 10,
          "需求⑭：网格列数 9 → 10（表头与数据行一致，不会错位）", f"列数={_col_count(html)}")
    _api("POST", "/api/reset")

    # ===================== 二、客户端按钮闭环（真浏览器） =====================
    print("\n===== 二、客户端：编辑→保存→提交 三态（真浏览器）=====")
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
        print("\n（服务端一段已跑完）")
        return 3

    from playwright.sync_api import sync_playwright            # noqa: PLC0415
    from framework.tools.common.browser import launch_opts      # noqa: PLC0415

    def _ready(page, timeout=8000):
        page.wait_for_function("() => document.body.dataset.hybridReady === '1'", timeout=timeout)

    with sync_playwright() as p:
        b = p.chromium.launch(**launch_opts(headless=True))
        page = b.new_context().new_page()
        page.goto(f"{DEMO}/order_detail.html?no={ORDER}&demo_role={TEST_ROLE}", wait_until="networkidle")
        _ready(page)

        # 查看态：三个按钮都在、文案「编辑」、无 dirty 标记
        check(page.locator("#btn-detail-cancel").is_visible() and
              page.inner_text("#btn-detail-edit").strip() == "编辑",
              "查看态：取消 / 编辑 / 提交 都在，按钮文案是「编辑」")
        check(page.inner_text("#d-dirty").strip() == "", "查看态：没有未保存标记")

        # 需求⑬：只读态 ⇒ 表单3 三个按钮置灰、全部关闭可用
        check(page.locator("#btn-add-line").is_disabled() and page.locator("#btn-save-lines").is_disabled()
              and page.locator("#btn-cancel-lines").is_disabled(),
              "需求⑬：只读态「新增行/保存/取消」都是 disabled（置灰）")
        check(page.locator("#btn-close-all-lines").is_enabled(),
              "需求⑬：只读态「全部关闭」仍可用（不受编辑态限制）")

        # 需求⑭：勾一条 ⇒ 「关闭」只关那一条；未勾选 ⇒ 只提示不动作
        page.click("#btn-close-lines")
        page.wait_for_timeout(300)
        check("请先勾选" in page.inner_text("#detail-status"),
              "需求⑭：未勾选就点「关闭」⇒ 只提示、不动作", page.inner_text("#detail-status")[:36])
        page.locator(".ln-pick").first.check()
        page.click("#btn-close-lines")
        page.wait_for_function(
            "() => document.getElementById('detail-status').textContent.includes('已关闭')", timeout=6000)
        _ln = _api("GET", f"/api/order/lines?no={ORDER}")[1].get("lines") or []
        check(sum(1 for x in _ln if x.get("closed")) == 1,
              "需求⑭：勾一条 + 关闭 ⇒ 服务端只有那一条 closed", f"closed={[x.get('line_no') for x in _ln if x.get('closed')]}")
        check(page.locator(".ln-pick:checked").count() == 0, "需求⑭：关闭后清空勾选")
        # 表头全选 ⇒ 关闭 ⇒ 全部行关闭（订单整体状态 = 已关闭）
        page.check("#chk-all-lines")
        page.click("#btn-close-lines")
        page.wait_for_function(
            "() => document.getElementById('detail-status').textContent.includes('所有行已关闭')", timeout=6000)
        _ln2 = _api("GET", f"/api/order/lines?no={ORDER}")[1].get("lines") or []
        check(all(x.get("closed") for x in _ln2) and _ln2,
              "需求⑭：全选 + 关闭 ⇒ 所有行都关闭", f"行数={len(_ln2)}")

        # 点「编辑」⇒ 取消消失 + 文案变「保存」+ 提交不变
        page.click("#btn-detail-edit")
        page.wait_for_timeout(200)
        check(page.locator("#btn-detail-cancel").count() == 0,
              "编辑态：**取消按钮消失**")
        check(page.inner_text("#btn-detail-edit").strip() == "保存",
              "编辑态：同一个按钮文案变「保存」", str(page.inner_text("#btn-detail-edit").strip()))
        check(page.locator("#btn-detail-submit").is_visible() and
              page.inner_text("#btn-detail-submit").strip() == "提交",
              "编辑态：「提交」按钮不变")

        # 改字段 ⇒ dirty
        page.fill("#d-name", "编辑态改名")
        page.wait_for_timeout(150)
        check("有未保存修改" in page.inner_text("#d-dirty"), "改了字段 ⇒ 出现「有未保存修改」标记")
        check(page.locator("#btn-add-line").is_enabled() and page.locator("#btn-save-lines").is_enabled()
              and page.locator("#btn-cancel-lines").is_enabled(),
              "需求⑬：进编辑态后「新增行/保存/取消」变为可用（高亮）")

        # 点「提交」⇒ 被拦（提示 + 未触发履行）
        page.click("#btn-detail-submit")
        page.wait_for_timeout(400)
        st_txt = page.inner_text("#detail-status")
        check("未保存" in st_txt, "负向：未保存就点「提交」⇒ 状态行提示、**不提交**", st_txt[:40])
        check(_api("GET", f"/api/order/fulfill?no={ORDER}")[1].get("submitted") is False,
              "负向：履行确实没被触发（服务端 submitted=False）")

        # 点「保存」⇒ 落库 + 回查看态 + dirty 归零
        page.click("#btn-detail-edit")
        page.wait_for_function(
            "() => document.getElementById('detail-status').textContent.includes('已保存')", timeout=8000)
        check(_order().get("name") == "编辑态改名", "正向：保存后服务端字段已更新",
              _order().get("name"))
        check(page.locator("#btn-detail-cancel").is_visible() and
              page.inner_text("#btn-detail-edit").strip() == "编辑",
              "保存后：回到查看态（取消回来、按钮变回「编辑」）")
        check("有未保存修改" not in page.inner_text("#d-dirty"), "保存后：dirty 标记消失")

        # 再点「提交」⇒ 放行
        page.click("#btn-detail-submit")
        page.wait_for_timeout(600)
        check(_api("GET", f"/api/order/fulfill?no={ORDER}")[1].get("submitted") is True,
              "正向：保存后再点「提交」⇒ 履行真的被触发")
        b.close()

    _api("POST", "/api/reset")
    print()
    if fails:
        print(f"❌ {len(fails)} 条判据不符预期：")
        for f in fails:
            print(f"   · {f}")
        return 1
    print("全部符合预期 ✅（服务端保存口径对、未保存必须拦得住、保存后提交放行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
