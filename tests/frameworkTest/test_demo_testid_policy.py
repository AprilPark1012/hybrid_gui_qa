"""demo 埋点政策的判据（一类 · 秒级 · 不需 demo/浏览器）—— P16 批 1「判据先行」第 ① 组。

**背景（AprilPark1012 2026-09-22 现场反馈）**：demo 里几乎每个可交互元素都挂了 `data-testid`
（含行 `row-*`、单元格 `cell-*`、行内链接 `link-HT-1001`、弹层候选行 `pick-*`），与他项目实际不符
（实际一般**只有顶层元素**有埋点）⇒ 框架的"从顶层锚点下钻到子元素"能力**从没被真实触发过**。
本判据 = **防回退闸门**：撤掉之后，谁再把行内埋点加回来，这里必须红。

**红态预期**：批 4（改 demo）之前**必然红**（30 处违规）—— 这是判据先行的正常形态，不是 bug。

**口径演进（同日）**：批 4 只撤"行/单元格/行内"（口径 A，保留顶层控件）⇒ 需求方当场收紧成
**口径 C：只有结构容器允许埋点**（页面级也一样、弹层内部只有容器）⇒ **批 6 再撤 85 处**。
理由：demo 留内层埋点 = 给框架一条**生产里不存在的捷径** ⇒ 可用性/正确性/健壮性无从保证。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "frameworkTest"))
import testid_policy as tp          # noqa: E402

DEMO_DIR = REPO / "demo"
FIXTURE = REPO / "tests" / "featureTest" / "fixtures" / "zero_testid_page.html"


# ---------------- ① 判据自身的负向自证（R7：只跑正向不算验证过）----------------

def test_scanner_catches_row_level_testid():
    """★ 负向：行级 `tr` 埋点必须被抓（这是 `row-${c.no}` 的形态）。"""
    html = '<table><tbody><tr data-testid="row-HT-1001"><td>HT-1001</td></tr></tbody></table>'
    v = tp.scan_html(html)
    assert len(v) == 1 and v[0]["tag"] == "tr", v
    assert any("行/单元格" in r for r in v[0]["reasons"]), v[0]


def test_scanner_catches_cell_and_inline_link():
    """★ 负向：单元格埋点 + 行内链接埋点都必须被抓（`cell-no` / `link-HT-1001` 的形态）。"""
    html = ('<table><tbody><tr><td data-testid="cell-no">'
            '<a data-testid="link-HT-1001" href="/d">HT-1001</a></td></tr></tbody></table>')
    tags = {x["tag"] for x in tp.scan_html(html)}
    assert tags == {"td", "a"}, f"单元格与行内链接都要被抓：{tp.scan_html(html)}"


def test_scanner_catches_script_template_render():
    """★ 负向：`<script>` 里逐行渲染出来的埋点也要抓（前端模板 = 运行时每行都有）。"""
    html = '<table><tbody></tbody></table><script>tb.innerHTML = `<tr data-testid="orow-${o.no}"><td>x</td></tr>`;</script>'
    v = tp.scan_html(html)
    assert v and any("script" in r for r in v[0]["reasons"]), v


def test_scanner_allows_containers_only():
    """★ 正向（防误伤）：**只有结构容器**放行 —— 口径 C（2026-09-22 收紧：页面级也一样，只有顶层有埋点）。"""
    html = ('<table data-testid="tbl-contracts"><thead><tr><th>编号</th></tr></thead><tbody></tbody></table>'
            '<span data-testid="page-info">第 1 / 3 页</span>'
            '<span data-testid="pager"></span><div data-testid="modal-new" class="modal"></div>')
    v = tp.scan_html(html)
    assert v == [], f"结构容器被误判为违规（误伤会让人把闸门关掉）：{v}"


def test_scanner_catches_control_testid_on_page():
    """★ 负向（口径 C 新增）：**页面级交互控件**上的埋点也要抓（输入框/按钮/链接都不许留）。"""
    html = ('<input data-testid="tb-keyword" placeholder="关键字">'
            '<button data-testid="btn-search">搜索</button>'
            '<a data-testid="link-orders" href="/o">订单</a>')
    v = tp.scan_html(html)
    assert {x["tag"] for x in v} == {"input", "button", "a"}, v
    assert all(any("交互控件" in r for r in x["reasons"]) for x in v), v


def test_scanner_catches_testid_inside_popup():
    """★ 负向（口径 C 新增）：**弹层内部**（非容器）一律违规 —— 生产里弹层只有顶层挂埋点。"""
    html = ('<div data-testid="modal-x" class="modal">'
            '<input data-testid="inp-name" placeholder="名称">'
            '<table data-testid="tbl-pick-x"><tbody></tbody></table></div>')
    v = tp.scan_html(html)
    flagged = {x["testid"] for x in v}
    assert flagged == {"inp-name", "tbl-pick-x"}, f"弹层内层（字段 + 内层表格）都要被抓：{v}"
    assert all(any("弹层内部" in r for r in x["reasons"]) for x in v), v


def test_scanner_allows_popup_container_itself():
    """★ 正向：弹层**容器本身**放行（它就是那个"顶层"）。"""
    html = '<div class="modal" data-testid="modal-x"><div class="modal-box"><h3>选择客户</h3></div></div>'
    assert tp.scan_html(html) == [], tp.scan_html(html)


def test_scanner_allows_clean_page():
    assert tp.scan_html("<div><button>搜索</button></div>") == []


# ---------------- ② demo 现状（批 4 之前必然红）----------------

def test_demo_has_no_row_cell_or_inline_testid():
    """★ 核心判据：demo 里不许再有行级 / 单元格级 / 行内元素的 `data-testid`。

    允许保留：**只有结构容器**（页面级 table/pager/status/状态区 + 弹层容器）—— 口径 C。
    口径 A（顶层控件保留）已于 2026-09-22 作废：他要"和实际生产环境一样，只有顶层才有 testid"。
    """
    found = tp.scan_dir(DEMO_DIR)
    assert found == {}, (
        "demo 仍有行内/单元格级埋点（真实项目里这些位置通常没有 testid ⇒ 框架必须下钻）：\n"
        + tp.format_violations(found))


# ---------------- ③ 夹具自证：零 testid 夹具页不许退化 ----------------

def test_zero_testid_fixture_is_really_zero():
    """★ 防夹具退化：夹具页一旦被人顺手加上 testid，"零埋点"这条能力就再也没被验过。"""
    assert FIXTURE.exists(), f"缺夹具页：{FIXTURE}"
    html = FIXTURE.read_text(encoding="utf-8")
    # 只看**元素属性**（注释里提到 data-testid 不算埋点 —— 判据不许被注释里的字面误伤）
    assert not re.search(r"<[^>]*\sdata-testid\s*=", html), \
        "夹具页必须是**零 testid**（它是「最坏真实系统」的替身）"


def test_zero_testid_fixture_keeps_the_hard_cases():
    """夹具必须保留三样硬骨头：无 data-field 的表格 / 同名控件（歧义）/ 无 testid 的容器锚点。"""
    html = FIXTURE.read_text(encoding="utf-8")
    assert not re.search(r"<[^>]*\sdata-field\s*=", html), \
        "夹具刻意**不带** data-field ⇒ 逼出「表头文本 + 列序」降级路径"
    assert html.count(">选择<") >= 4, "夹具必须含同名「选择」（按钮 + 链接各两行）⇒ 歧义负向"
    assert 'aria-label="工具栏"' in html, "夹具必须含无 testid 的容器锚点（aria-label）"
    assert html.count("关键字") >= 2, "夹具必须含同名输入框（工具栏 + 弹层）⇒ 容器锚点参与消歧"


def test_zero_testid_fixture_covers_column_order_fallback():
    """夹具的表格必须有**中文表头**且列序稳定 ⇒ 「无 data-field 时按表头文本 + 列序」这条降级路径可验。"""
    html = FIXTURE.read_text(encoding="utf-8")
    for header in ("单号", "供应商", "金额", "操作"):
        assert f"<th>{header}</th>" in html, f"夹具表头缺 {header}"
