"""`wait_text` 的 `refresh` 策略 · 渲染契约（P22 批 1 · J4）—— 秒级，不需 demo/浏览器。

要解决的问题（P22 §二 2c · 实测真值）：
  `demo/orders.html` 里 `setInterval / setTimeout / refresh` **命中 0 处** ⇒ 订单列表页**不会自己刷新**
  ⇒ 「等它流转到已关闭」这件事，光靠 playwright 的 expect 轮询 DOM **永远等不到**
  （那行文本永远不会自己变）⇒ 必须给等待式断言一个**每轮重新取数**的方式。

三态口径（AprilPark1012 2026-09-29 拍：新增等待式断言，带超时 + 每轮重新取数）：
  · `none`（缺省）：只轮询 DOM —— 等价现有 expect 语义，用于"页面自己会更新"的场景
  · `reload`：每轮重新加载当前 URL
  · `research`：每轮重新触发**上一次搜索**（框架记住最后一次「搜索」点击 + 当时输入，轮询时重放）
    （`research` 的**重放实现**由 V3 端到端验证 —— 本判据只钉"参数被如实渲染 / 非法值必须红"，
     不把重放的内部 API 写死，避免判据反过来绑死实现）

判据口径（J4）：
  1. 三态各自渲染正确（`refresh="none"|"reload"|"research"` 都出现在产物里）
  2. 缺省（不写 refresh）⇒ 不产生任何 refresh 参数（保持与老产物形态一致）
  3. **负向**：非法 `refresh` 值（`"full"` / 空串以外的拼写错）⇒ 必须 `pytest.fail`
  4. **负向**：`refresh` 传错类型（数字 / 列表）⇒ 必须 `pytest.fail`

跑法（秒级）：
    python -m pytest tests/特性8-质量闸门体系/test_wait_text_refresh_policy.py -q
"""
from __future__ import annotations

import pytest

from framework.tools.generate import generator as G


def _render(a: dict) -> str:
    """把一条断言渲染成生成脚本里的调用行（与 generate 同一入口，避免判据走"影子实现"）。

    ⚠️ 必须补 `_payload_ref`：真实链路里期望值由 `_add_payload_refs()` 抽离成 `_data(ref, ctx)`，
    没有它会被通用检查判成「缺少 expect」⇒ 判据不带它就等于测了个假形态。
    （首次写就踩：5 条**正向**判据全红，原因不是实现没生效，而是判据漏了这个字段。）
    """
    a = dict(a)
    if a.get("expect") is not None and not a.get("_payload_ref"):
        a["_payload_ref"] = "expect"
    return "\n".join(G._render_assert(a, {}, cross_page=False, dup_raw=set()))


@pytest.mark.parametrize("mode", ["none", "reload", "research"])
def test_refresh_modes_rendered(mode):
    """判据 1：三态都如实渲染（缺一不可 —— `research` 是列表页不刷新那条缺口的解药）。"""
    src = _render({"kind": "wait_text", "expect": "已关闭", "timeout_ms": 60000, "refresh": mode})
    assert "pytest.fail" not in src, f"refresh={mode!r} 应合法，实际：{src}"
    assert "_assert_wait_text(" in src, f"应渲染成等待式断言：{src}"
    assert mode in src, f"refresh={mode!r} 必须落在产物里（否则等于没声明）：{src}"


def test_default_refresh_is_absent():
    """判据 2：不写 refresh ⇒ 不产生 refresh 参数（老产物形态不变，避免全量重渲染）。"""
    src = _render({"kind": "wait_text", "expect": "已关闭", "timeout_ms": 60000})
    assert "refresh=" not in src, f"未声明 refresh 时不该出现该参数：{src}"


@pytest.mark.parametrize("bad", ["full", "re-search", "NONE", 3, ["reload"]])
def test_negative_bad_refresh_must_fail(bad):
    """判据 3/4（负向）：非法取值或类型 ⇒ 必须当场 fail（拼错一个词就静默退成"只等不重取" = 假绿）。"""
    src = _render({"kind": "wait_text", "expect": "已关闭", "timeout_ms": 60000, "refresh": bad})
    assert "pytest.fail" in src and "未知断言类型" not in src, (
        f"refresh={bad!r} 非法却渲染成了正常调用（或失败原因是「未实现」而非「值非法」）：{src}")
