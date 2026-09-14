"""断言类型契约的快速回归（不需要 demo、不需要浏览器、秒级）。

盯三件事：
  1. 每种 kind 翻译到正确的 conftest 辅助函数（改映射时立刻发现漂移）；
  2. 结构性错误（未知 kind / 缺 expect / 缺 name / 缺定位 / 元素未映射）**必须 pytest.fail**，
     绝不允许「少验一步还报绿」；
  3. `expect` 为空串时仍要落进数据集（value 断言验「被清空」就是靠这个）。
"""
from __future__ import annotations

import pytest

from framework.generator import (_ASSERT_KINDS, _add_payload_refs, _extract_data,
                                 _render_assert)

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
    """_ASSERT_KINDS 里声明的每个 kind 都要真的被翻译（防「声明了但没实现」）。"""
    for kind in _ASSERT_KINDS:
        out = _render({"kind": kind, "expect": "x", "selector": "#s", "name": "n"})
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
