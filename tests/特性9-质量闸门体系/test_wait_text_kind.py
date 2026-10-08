"""`wait_text` 等待式断言 · 渲染契约（P22 批 1 · J3）—— 秒级，不需 demo/浏览器。

起因（真值 · P22 §二 缺口 (2)）：
  · 11 种断言 kind 里没有"等状态变化"（`generator.py:149-155`）
  · `_assert_text` 超时**硬编码 5000ms**（`generator.py:1945`），连 `HYBRID_LOCATE_TIMEOUT` 都调不到，
    断言层也没有 per-assert timeout 字段
  · [!] 更要命的是 `demo/orders.html` **无任何自动刷新**（grep `setInterval/setTimeout/refresh` = 0 处）
    -> 光把超时调大**也等不到**，必须"每轮重新取数"（由 J4 的 `refresh` 三态负责）
AprilPark1012 2026-09-29 拍板：**新增等待式断言 `wait_text`**（带超时 + 每轮重新取数）。

判据口径（J3）：
  1. 正向：`kind=wait_text` + `expect` + `timeout_ms` -> 渲染出 `_assert_wait_text(...)` 且带上该毫秒值
  2. 正向：`wait_text` 已登记进 `_ASSERT_KINDS`（否则渲染层直接判"未知断言类型"）
  3. 正向：不写 `timeout_ms` -> 用**有界默认值**（必须是正整数毫秒，绝不无限等）
  4. 负向：缺 `expect` -> 必须 `pytest.fail`（不许静默少验一步 = 假绿）
  5. 负向：`timeout_ms` 非法（负数 / 0 / 非数字）-> 必须 `pytest.fail`（不许静默取默认）
  6. 回归：11 种老 kind 仍在册（新增 kind 不许挤掉老的）

跑法（秒级）：
    python -m pytest tests/特性9-质量闸门体系/test_wait_text_kind.py -q
"""
from __future__ import annotations

import re

import pytest

from framework.tools.generate import generator as G

_OLD_KINDS = {"text", "visible", "hidden", "count", "attr", "value", "url",
              "checked", "unchecked", "enabled", "disabled", "first_row"}


def _render(a: dict) -> str:
    """把一条断言渲染成生成脚本里的调用行（与 generate 同一入口，避免判据走"影子实现"）。

    [!] 必须补 `_payload_ref`：真实链路里期望值由 `_add_payload_refs()` 抽离成 `_data(ref, ctx)`，
    没有它会被通用检查判成「缺少 expect」-> 判据不带它就等于测了个假形态。
    （首次写就踩：5 条**正向**判据全红，原因不是实现没生效，而是判据漏了这个字段。）
    """
    a = dict(a)
    if a.get("expect") is not None and not a.get("_payload_ref"):
        a["_payload_ref"] = "expect"
    return "\n".join(G._render_assert(a, {}, cross_page=False, dup_raw=set()))


def test_wait_text_registered_in_kinds():
    """判据 2：`wait_text` 必须在册 —— 否则渲染层会直接判"未知断言类型"。"""
    assert "wait_text" in G._ASSERT_KINDS, (
        f"wait_text 未登记进 _ASSERT_KINDS（现有：{sorted(G._ASSERT_KINDS)}）-> 用例写它必被当成非法类型")


def test_wait_text_renders_with_timeout():
    """判据 1：带超时渲染成 `_assert_wait_text(...)`，且毫秒值如实落到产物里。"""
    src = _render({"kind": "wait_text", "expect": "已关闭", "timeout_ms": 180000})
    assert "pytest.fail" not in src, f"不应被判非法：{src}"
    assert "_assert_wait_text(" in src, f"应渲染成等待式断言调用：{src}"
    assert "180000" in src, f"180000ms 必须原样落进产物（否则等的不是他要的时长）：{src}"
    # 期望值走**数据引用**：真实链路里它被抽到 scripts/datasets/*.json，生成代码里只有
    # `_data('expect', ctx)` —— 判据不该断言字面量出现在生成代码里（首次就是这么写错的）
    assert "_data(" in src, f"期望值必须经数据引用传入（与 text 断言同口径）：{src}"


def test_wait_text_default_timeout_is_bounded():
    """判据 3：不写 `timeout_ms` -> 用**有界**默认（正整数毫秒），绝不无限等。"""
    src = _render({"kind": "wait_text", "expect": "已关闭"})
    assert "pytest.fail" not in src, f"缺 timeout_ms 应走默认值而不是判非法：{src}"
    m = re.search(r"timeout_ms=(\d+)", src)
    assert m, f"默认超时必须显式落在产物里（便于审计「到底等了多久」）：{src}"
    assert int(m.group(1)) > 0, f"默认超时必须 > 0：{src}"


def test_negative_missing_expect_must_fail():
    """判据 4（负向）：`wait_text` 没有 `expect` -> 必须 fail（等一个没写的东西 = 假绿）。"""
    src = _render({"kind": "wait_text", "timeout_ms": 1000})
    assert "pytest.fail" in src and "未知断言类型" not in src, (
        f"缺 expect 必须**因为缺 expect**失败（不能是「kind 还没实现」这种失败，否则判据恒真）"
        f"—— 实际渲染：{src}")


@pytest.mark.parametrize("bad", [-1, 0, "abc", 3.5])
def test_negative_bad_timeout_ms_must_fail(bad):
    """判据 5（负向）：非法 `timeout_ms` -> 必须 fail（不许静默退回默认值糊过去）。"""
    src = _render({"kind": "wait_text", "expect": "已关闭", "timeout_ms": bad})
    assert "pytest.fail" in src and "未知断言类型" not in src, (
        f"timeout_ms={bad!r} 非法却渲染成了正常调用（或失败原因是「未实现」而非「值非法」）：{src}")


def test_old_kinds_not_broken():
    """判据 6（回归）：新增 kind 不许挤掉老的 11 种。"""
    missing = _OLD_KINDS - set(G._ASSERT_KINDS)
    assert not missing, f"老断言 kind 丢了：{sorted(missing)}"
