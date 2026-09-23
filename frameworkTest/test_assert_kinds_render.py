"""断言类型契约的快速回归（不需要 demo、不需要浏览器、秒级）。

盯三件事：
  1. 每种 kind 翻译到正确的 conftest 辅助函数（改映射时立刻发现漂移）；
  2. 结构性错误（未知 kind / 缺 expect / 缺 name / 缺定位 / 元素未映射）**必须 pytest.fail**，
     绝不允许「少验一步还报绿」；
  3. `expect` 为空串时仍要落进数据集（value 断言验「被清空」就是靠这个）。
"""
from __future__ import annotations

import pytest

import framework.tools.generate.generator as gen
from framework.tools.generate.generator import (_ASSERT_KINDS, _add_payload_refs, _dup_raw_names_for_case,
                                 _extract_data, _render_assert, _render_pytest_case)

LOC = {"搜索": 'get_by_test_id("btn-search")'}


def _prep(a: dict) -> dict:
    """走和 generate 一样的管线：先加 _payload_ref，再渲染。"""
    return _add_payload_refs({"asserts": [a]})["asserts"][0]


def _render(a: dict) -> str:
    return "\n".join(_render_assert(_prep(a), LOC))


@pytest.mark.parametrize("kind,extra,helper", [
    ("text", {"expect": "HT-1005"}, "_assert_text(page"),
    ("url", {"expect": "localhost:8000"}, "_assert_url(page"),
    ("visible", {"selector": "#modal-new"}, "_assert_visible(page"),
    ("hidden", {"selector": "#modal-new"}, "_assert_hidden(page"),
    ("count", {"selector": "#tbody tr", "expect": 3}, "_assert_count(page"),
    ("attr", {"selector": "#t td", "name": "data-field", "expect": "x"}, "_assert_attr(page"),
    ("value", {"selector": "#tb", "expect": ""}, "_assert_value(page"),
    ("checked", {"selector": "#c"}, "_assert_checked(page"),
    ("unchecked", {"selector": "#c"}, "_assert_unchecked(page"),
    ("enabled", {"selector": "#b"}, "_assert_enabled(page"),
    ("disabled", {"selector": "#b"}, "_assert_disabled(page"),
])
def test_kind_maps_to_helper(kind, extra, helper):
    out = _render({"kind": kind, "desc": "d", **extra})
    assert helper in out
    assert "pytest.fail" not in out
    assert "RuntimeError" not in out


def test_kind_defaults_to_text_when_absent():
    """老用例只有 expect、没有 kind —— 必须继续按 text 断言跑（向后兼容）。"""
    out = _render({"desc": "d", "expect": "HT-1005"})
    assert "_assert_text(page" in out


def test_selector_wins_over_element():
    out = _render({"kind": "visible", "selector": "#modal-new", "element": "搜索"})
    assert "locator('#modal-new')" in out and "btn-search" not in out


def test_element_maps_via_loc_map():
    out = _render({"kind": "enabled", "element": "搜索"})
    assert "btn-search" in out and "semantic='搜索'" in out


# ---------- 结构性错误：必须显式失败，不许静默跳过 ----------
@pytest.mark.parametrize("a,keyword", [
    ({"kind": "color", "expect": "red"}, "未知断言类型"),
    ({"kind": "count", "selector": "#t"}, "缺少 expect"),
    ({"kind": "attr", "selector": "#t", "expect": "x"}, "缺少 name"),
    ({"kind": "visible"}, "需要 selector 或 element"),
    ({"kind": "enabled", "element": "根本不存在的控件"}, "元素未映射"),
])
def test_structural_errors_fail_loud(a, keyword):
    out = _render(a)
    assert "pytest.fail" in out, "结构性错误必须 pytest.fail，不能静默跳过"
    assert keyword in out


def test_render_covers_every_declared_kind():
    """_ASSERT_KINDS 里声明的每个 kind 都要真的被翻译（防「声明了但没实现」）。

    ⚠️ 样例必须给全「该 kind 的必备字段」：first_row 用 row_field 定位第一行的某一列
    （它不需要 selector/element），缺字段时会走 pytest.fail —— 那是**结构性错误**的正确行为，
    不能把它当成「没实现翻译」（2026-09-17 加 first_row 时就是这么红的）。
    """
    for kind in _ASSERT_KINDS:
        out = _render({"kind": kind, "expect": "x", "selector": "#s", "name": "n",
                       "row_field": "orderName"})
        assert "pytest.fail" not in out, f"{kind} 没有实现翻译：{out}"


# ---------- 数据抽离：空串/0 也是合法期望值 ----------
def test_empty_string_expect_still_extracted():
    case = {"asserts": [{"kind": "value", "selector": "#tb", "expect": ""}]}
    data = _extract_data(case)
    assert "expect_0" in data and data["expect_0"] == ""
    prepped = _prep(case["asserts"][0])
    assert prepped["_payload_ref"] == "expect_0"
    out = "\n".join(_render_assert(prepped, LOC))
    assert "_data('expect_0', ctx)" in out


def test_zero_count_expect_still_extracted():
    data = _extract_data({"asserts": [{"kind": "count", "selector": "#t", "expect": 0}]})
    assert data.get("expect_0") == 0


# ---------------------------------------------------------------------------
# 跨页重名「原始名」告警必须**按用例**判定（2026-09-18 实测的假红）
#
# 背景：`_DUP_PAGES` 是所有用例声明页面的并集 —— 订单场景带来「订单系统」页后，
# 它和「列表页」都有 HT_1001…HT_1020 链接 ⇒ HT_1005 进并集；而手写跨页用例
# （列表页+详情页，如 cross_page_detail / ai_contracts_cross_page_011030）在自己的范围里
# 根本不重名，却被全局名单判成「必须写 @页名」⇒ cli run 15 passed / 2 failed（假红）。
# 判据：本用例声明的页 ∩ 该名字出现的页 ≥ 2。
# ---------------------------------------------------------------------------

def _pages(*names):
    return [{"name": n} for n in names]


def test_dup_raw_names_are_scoped_to_the_case():
    gen._DUP_PAGES.clear()
    gen._DUP_PAGES.update({"HT_1005": {"列表页", "订单系统"}})
    assert _dup_raw_names_for_case({"pages": _pages("列表页", "详情页")}) == set(), \
        "别的用例带进来的重名不该算到本用例头上"
    assert _dup_raw_names_for_case({"pages": _pages("列表页", "订单系统")}) == {"HT_1005"}
    assert _dup_raw_names_for_case({"pages": _pages("列表页")}) == set(), "单页用例不适用"


def test_render_does_not_flag_unrelated_case_but_does_flag_real_one():
    gen._DUP_PAGES.clear()
    gen._DUP_PAGES.update({"HT_1005": {"列表页", "订单系统"}})
    loc = {"HT_1005": 'get_by_test_id("row-HT-1005-no")'}

    unrelated = {"case_id": "cross_page_detail", "pages": _pages("列表页", "详情页"),
                 "steps": [{"op": "click", "element": "HT_1005", "desc": "点编号进详情页"}]}
    out = _render_pytest_case(unrelated, loc)
    assert "跨页重名" not in out and "pytest.fail" not in out, out

    real = {"case_id": "orders_ish", "pages": _pages("列表页", "订单系统"),
            "steps": [{"op": "click", "element": "HT_1005", "desc": "同上"}]}
    out2 = _render_pytest_case(real, loc)
    assert "跨页重名" in out2 and "pytest.fail" in out2, out2


def test_render_assert_respects_explicit_dup_raw():
    """断言侧同样按用例口径：显式传入 dup_raw=set() 时，即便全局名单里有这个名字也不拦。"""
    gen._DUP_RAW_NAMES.clear()
    gen._DUP_RAW_NAMES.add("HT_1005")
    loc = {"HT_1005": 'get_by_test_id("detail-no")'}
    a = _prep({"kind": "text", "expect": "HT-1005", "element": "HT_1005",
               "desc": "详情页出现编号"})
    assert "pytest.fail" not in "\n".join(_render_assert(a, loc, cross_page=True, dup_raw=set()))
    assert "跨页重名" in "\n".join(_render_assert(a, loc, cross_page=True, dup_raw={"HT_1005"}))
