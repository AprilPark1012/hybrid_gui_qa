"""wait_text 的「限定范围」契约（P22 批 5；不需 demo/浏览器，秒级）。

为什么（真值 2026-09-30）：
  订单状态流转断言 `expect="已关闭"` 用全页 `get_by_text` -> 命中**隐藏**的筛选下拉选项
  `<option value="已关闭">`（demo/orders.html:531）-> 永远不可见 -> 5s 超时失败。
  正解是限定范围：在状态列 `td[data-field="orderStatus"]` 里等这段文本。

判据：
  1. 带 selector -> 渲染出 selector 参数；
  2. 不带 -> 渲染出空 selector（向后兼容，行为不变）。
"""
from __future__ import annotations

from framework.tools.generate.generator import _add_payload_refs, _render_assert

LOC: dict = {}


def _render(a: dict) -> str:
    return "\n".join(_render_assert(_add_payload_refs({"asserts": [a]})["asserts"][0], LOC))


def test_wait_text_passes_selector_through():
    out = _render({"kind": "wait_text", "expect": "已关闭",
                   "selector": 'td[data-field="orderStatus"]',
                   "timeout_ms": 240000, "desc": "等状态列变已关闭"})
    assert "_assert_wait_text(page" in out and "selector=" in out, out
    assert "orderStatus" in out, out
    assert "pytest.fail" not in out, out


def test_wait_text_without_selector_is_backward_compatible():
    out = _render({"kind": "wait_text", "expect": "已关闭", "timeout_ms": 30000, "desc": "d"})
    assert "_assert_wait_text(page" in out and "selector=''" in out, out
    assert "pytest.fail" not in out, out
