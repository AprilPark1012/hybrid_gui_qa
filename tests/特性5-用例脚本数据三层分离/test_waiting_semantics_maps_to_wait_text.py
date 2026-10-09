# -*- coding: utf-8 -*-
"""特性5 · 「等待」语义必须落到**有界轮询**断言，不能退化成一次性断言（V8.4.2）。

事故（2026-10-09 端到端实测，Windows + 本机都复现）：
    AI 产出的断言写得很清楚 ——

        {"desc": "**有界等待**订单状态自动流转到已关闭", "expect": "已关闭", "after_step": 23}

    但 AI **没给 `kind`**，生成器兜底成 `kind="text"` => 渲染成 `_assert_text`
    （一次性 `wait_for(5000)`）。而这一条的语义是「**等状态自己流转过来**」，
    5 秒必然不够 => 实跑报：

        TimeoutError: Locator.wait_for: Timeout 5000ms exceeded
          - waiting for get_by_text("已关闭").first to be visible
            14 x locator resolved to hidden <option value="已关闭">已关闭</option>

    框架**早就有** `wait_text`（有界轮询 + 探到就走，`_assert_wait_text`），
    只是这层「等待语义 → wait_text」的映射缺了。

口径：
  · `desc` 里出现明确的等待语义（「等待 / 等到 / 流转到 / 等到…出现」等）且 AI **没指定 kind**
    => 兜底成 `wait_text`，并给一个**够用的默认超时**（不是无限等）。
  · AI **显式指定**了别的 kind => 一律尊重（不许覆盖模型的明确决定）。
  · 普通文本断言（没有等待语义）**不许**被误升级成轮询（否则把异步等待的坑变成慢用例）。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.tools.generate import generator as gen  # noqa: E402


def _kind_of(desc: str, kind=None, expect: str = "已关闭") -> str:
    a = {"desc": desc, "expect": expect, "after_step": 23}
    if kind is not None:
        a["kind"] = kind
    return gen.infer_kind_for_assert(a)


# ---------------------------------------------------------------- 等待语义 → wait_text

@pytest.mark.parametrize("desc", [
    "有界等待订单状态自动流转到已关闭",
    "等待状态变成已关闭",
    "等到列表出现刚创建的订单",
    "等待页面加载完成",
    "等出现「保存成功」提示",
    "等待审核状态更新",
])
def test_waiting_semantics_maps_to_wait_text(desc):
    """明确的「等待」措辞 -> `wait_text`（有界轮询），不是一次性断言。"""
    assert _kind_of(desc) == "wait_text", f"「{desc}」的等待语义被丢掉了"


def test_plain_text_assertion_is_not_upgraded():
    """**反向自证**：普通文本断言不许被升级成轮询（会把异步等待的坑变成慢用例）。"""
    assert _kind_of("确认到达订单列表页") == "text"
    assert _kind_of("确认搜到刚创建的发票") == "text"
    assert _kind_of("确认首行就是刚创建的订单") == "text"


def test_explicit_kind_is_respected():
    """AI 显式给了 kind -> 一律尊重（不许覆盖模型的明确决定）。"""
    assert _kind_of("有界等待状态变成已关闭", kind="text") == "text"
    assert _kind_of("等待状态变成已关闭", kind="count") == "count"
    assert _kind_of("等待状态变成已关闭", kind="url") == "url"


def test_wait_text_gets_a_finite_default_timeout():
    """`wait_text` 必须有**有限**默认超时 —— 不许变成无限等。"""
    a = {"desc": "有界等待订单状态自动流转到已关闭", "expect": "已关闭", "after_step": 23}
    gen.apply_kind_defaults(a)
    assert a["kind"] == "wait_text"
    tm = a.get("timeout_ms")
    assert isinstance(tm, int) and 0 < tm <= 120000, f"超时不合理：{tm!r}"
