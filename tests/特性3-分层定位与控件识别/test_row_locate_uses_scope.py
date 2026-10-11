# -*- coding: utf-8 -*-
"""判据：**行内定位（`row_index`）不得先走"要求语义唯一"的 `_loc()`**。

为什么（2026-10-11 真跑实测，V8.4.6 修）：
订单详情页「编辑 + 新增行」后，行内 `物料编码` 在每行都有一个同名输入框（实测页面匹配 **2 个**）。
`_act_row` 带着行号（`row_index=-1` 表示"最后一行"），却先调用 `_loc()` —— 那条路要求语义**唯一**，
于是 `resolve_locator` 直接返回
    `Tier1 语义 & Tier2 指纹均无法唯一确定`（ok=False）
=> 整步 `元素定位失败且自愈未成功: 物料编码@订单详情页`，**明明有行号也判死**。

正解：行内控件用探测期录下的「**锚点 + 容器内相对语义**」（`scope_locate`，本来就是干这个的）
拿**多命中 locator**，再 `.nth(行号)`；`_loc()` 只作退路（非行内控件走它）。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = (ROOT / "framework" / "tools" / "generate" / "generator.py").read_text(encoding="utf-8")


def _act_row_body() -> str:
    i = GEN.index("def _act_row(")
    j = GEN.find("\ndef ", i + 1)
    return GEN[i: j if j > 0 else len(GEN)]


def test_act_row_uses_scope_locate_for_multi_match_rows():
    """行内定位必须先试 `scope_locate`（多命中 + 按行取），而不是先要唯一。"""
    body = _act_row_body()
    assert "scope_locate(" in body, (
        "行内定位没有走 scope_locate -> 行内同名列控件会以『不唯一』为由判死"
        "（实测：页面 2 个同名输入框 + row_index=-1 也照样失败）")
    i_scope = body.index("scope_locate(")
    i_unique = body.index("_all = _loc(") if "_all = _loc(" in body else len(body)
    assert i_scope < i_unique, (
        "`_loc()`（要求唯一）出现在 scope_locate 之前 -> 又变成『先判死再兜底』")


def test_act_row_keeps_hard_failures_honest():
    """不许因为改了定位方式就静默退化：0 命中 / 越界仍然必须**明确报错**。"""
    body = _act_row_body()
    assert "匹配 **0 个**" in body, "0 命中不再明确报错（会静默取错行）"
    assert "越界" in body, "越界不再明确报错"
    assert "_all.nth(" in body, "没有按行号取行（nth）"


def test_row_select_without_value_matches_non_row_semantics():
    """**同一语义同一口径**：行内 select 没给 value 也要按「选第一项」（跳过空占位），不能一处能跑一处必炸。

    实测事故（2026-10-11）：AI 产出的行内 select 只给 `element`（desc 写「选第一行行类型」），
    非行内路径 V8.4 就定成「选第一项」了，行内路径却抛 `按行定位的 select 必须给 value`
    => 真跑红，看起来像"框架不支持"。
    """
    body = _act_row_body()
    assert "跳过空占位" in body or "真选项" in body, \
        "行内 select 未给 value 时没有按「选第一项」处理（会与 `_act` 口径不一致）"
    assert "select_option(index=" in body, "行内 select 没有按索引选第一项"
    assert "没有任何可选选项" in body, "真没选项时必须明确报错（不许静默）"


def test_scope_locate_is_the_single_shared_entry():
    """`scope_locate` 必须是**共用**入口：resolve_locator 与行内定位都走它，不各写一份。"""
    bridge = (ROOT / "framework" / "tools" / "probe" / "locator_bridge.py").read_text(encoding="utf-8")
    assert "scope_locate(" in bridge, "resolve_locator 没走 scope_locate（会出现第二套锚点解析）"
    assert "def scope_locate(" in (ROOT / "framework" / "tools" / "probe" / "scope_locate.py").read_text(
        encoding="utf-8"), "scope_locate 不在 probe/scope_locate.py（被谁私藏了一份？）"
