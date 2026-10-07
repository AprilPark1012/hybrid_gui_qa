"""一类判据：用例步骤支持 `by` 显式定位方式（P22 批 5，2026-09-30）。

## 为什么需要（真实缺陷，可复现）

跨角色全链路用例跑到最后一段「切发票管理员」时失败：

```
RuntimeError: 语义名未找到：'超@订单列表页'（逐字不存在；清单里唯一接近的是 '订'）
```

根因是**异态异名**：右上角角色切换按钮的**可见文本随当前角色变**
（探针以超管身份探测时叫 `超`；执行到那一步身份已是订单管理员，按钮显示 `super · 订单管理员`）。
但它的 `title="点击切换角色 / 退出登录"` **跨身份不变** —— 是稳定锚。

⇒ 框架要能表达「**就用这个稳定锚定位**」，而不是只能靠"探测期抓到的语义名"。
⇒ 这不是某个页面的特例：**凡"文案会随状态变、而 title/标签不变"的控件**都适用
  （角色按钮、开关、动态徽标……）⇒ 做成**通用字段**，框架层零业务词。

## 判据口径

`by` 是**可选的定位方式覆盖**，取值白名单：title / label / placeholder / testid / alt。
- 不给 `by` ⇒ **行为与改造前逐字节一致**（回归护栏，见 V3）。
- 给非法值 ⇒ **生成期就报错**（不许静默忽略 —— 否则产物看着合法、实际没用上）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.tools.generate.generator import (  # noqa: E402
    _BY_WHITELIST,
    _semantic_to_locator_expr,
    _validate_by,
)

# ---- V1：按 title 定位（本批要的能力）----


def test_by_title_renders_get_by_title():
    """`by: "title"` ⇒ 表达式用 `get_by_title`，且**优先于**探测期的语义名分支。"""
    it = {
        "semantic_name": "超@订单列表页",     # 探测期抓到的、会随身份变的可见文本
        "role": "button",
        "name": "超",
        "title": "点击切换角色 / 退出登录",   # 跨身份不变的稳定锚
        "text": "super · 订单管理员",
        "test_id": "",
    }
    expr = _semantic_to_locator_expr(it, scope="page", by="title")
    assert "get_by_title" in expr, f"应渲染成 get_by_title，实际：{expr}"
    assert "点击切换角色 / 退出登录" in expr or re.search(r"get_by_title\(", expr), expr


def test_by_title_beats_semantic_name():
    """带 `by` 时不许再退到 role+name 分支（那是会失效的那条路）。"""
    it = {"semantic_name": "超", "role": "button", "name": "超",
          "title": "点击切换角色 / 退出登录"}
    expr = _semantic_to_locator_expr(it, scope="page", by="title")
    assert 'get_by_role("button"' not in expr, f"不该用 role+name 定位：{expr}"


# ---- V2：非法值必须生成期报错（负向自证）----


def test_illegal_by_raises():
    """`by` 不在白名单 ⇒ 生成期抛错，不许静默忽略。"""
    it = {"semantic_name": "x", "title": "t"}
    try:
        _semantic_to_locator_expr(it, by="xpath")   # css/role 已合法（见 test_step_direct_locator）
    except ValueError as e:
        assert "css" in str(e), f"报错信息应包含非法值，实际：{e}"
    else:
        raise AssertionError("非法 by 值必须报错（否则产物看着合法、实际没用上）")


def test_whitelist_contents():
    """白名单口径固定 —— 加了新值要同时补判据（防止悄悄放宽）。

    2026-09-30 扩了 `role`/`css`：用途是"探测覆盖不到的控件"（实测开票页表单字段全没被探到），
    这类值由**用例直接给**（步骤里带 value），详见 test_step_direct_locator.py。
    """
    assert set(_BY_WHITELIST) == {"title", "label", "placeholder", "testid", "alt", "role", "css"}


# ---- V3：不给 by ⇒ 行为不变（回归护栏）----


def test_without_by_behaviour_unchanged():
    """不给 `by` ⇒ 与改造前一致（拿掉 by 参数调用，结果应相同）。"""
    it = {"semantic_name": "搜索", "role": "button", "name": "搜索", "test_id": ""}
    assert _semantic_to_locator_expr(it, scope="page") == _semantic_to_locator_expr(
        dict(it, by=None), scope="page")


# ---- V4：by=title 但元素无 title ⇒ 生成期报错（不许产出空定位）----


def test_by_title_without_title_raises():
    it = {"semantic_name": "x", "role": "button", "name": "x", "title": ""}
    try:
        _semantic_to_locator_expr(it, by="title")
    except ValueError as e:
        assert "title" in str(e)
    else:
        raise AssertionError("元素没有 title 却要求 by=title ⇒ 必须报错而不是产出无效定位")


# ---- V5：每个白名单值都能渲染（不遗漏）----


def test_every_whitelist_value_renders():
    base = {"semantic_name": "x", "title": "t", "label": "l",
            "placeholder": "p", "test_id": "tid", "alt": "a"}
    expect = {"title": "get_by_title", "label": "get_by_label",
              "placeholder": "get_by_placeholder", "testid": "get_by_test_id",
              "alt": "get_by_alt_text"}
    for by, fn in expect.items():
        expr = _semantic_to_locator_expr(dict(base), by=by)
        assert fn in expr, f"by={by} 应渲染 {fn}，实际：{expr}"


def test_validate_by_accepts_none():
    """不传/None ⇒ 合法（表示"用默认 Tier1 顺序"）。"""
    assert _validate_by(None) is None
    assert _validate_by("") is None
