"""可展开容器识别（P22 批 1 · J1）—— **纯结构判据，不需要浏览器 / demo**。

起因（真值 · P22 §二 缺口 1a）：
  demo 右上角角色菜单 `#nu-menu` 初始 `style="display:none"`（`demo/auth.js:188`），而探针
  `probe.py:442` 会 `if not _visible(page, loc): continue` 跳过不可见元素
  （explorer 的 DOM 采集同口径，`explorer.py:1261`）
  -> 「切换为订单管理员」**根本不在清单里** -> 跨角色场景第 2 步无控件可引用
  （而本项目铁律：AI 不许自造语义名）。

方案（P22 §三 A）：用**结构判据**认出「隐藏容器 + 它的可见触发器」，
探测期点开一次再探一轮（复用 `_try_collect_modal_items` 的二次探测模式），
探完**关掉**（探测是只读动作）。

判据口径（J1 · 6 条，含 4 条负向）：
  1. 正向：隐藏容器（内含交互控件）+ 同父容器内 **DOM 在前的可见可点**兄弟 -> 判出该兄弟为 opener
  2. 正向：显式声明（容器的 `aria-controls` 指向某兄弟，或该兄弟 `aria-haspopup`）优先 -> `reason` 区分
  3. 负向：隐藏容器但**没有**可见可点兄弟 -> None（绝不在陌生页面上乱点）
  4. 负向：**可见**容器 -> None（它不是"待展开"的）
  5. 负向：隐藏容器里**不含**任何交互控件 -> None（纯文案的 hidden div 不是菜单）
  6. 负向：可见触发器在容器**之后**（DOM 顺序不对）-> None（避免点错元素）

跑法（秒级）：
    python -m pytest tests/特性2-语义识别与分层定位/test_expandable_menu_discovery.py -q
"""
from __future__ import annotations

import pytest

from framework.tools.probe.expandable import pick_expandable_opener


def _node(key, tag, *, visible, interactive=False, contains_interactive=False,
          order=0, aria_controls="", aria_haspopup=False):
    """构造一个「同父容器下的兄弟节点」描述 —— 与探针侧 JS 采集的字段一一对应（纯数据）。"""
    return {"key": key, "tag": tag, "visible": visible, "interactive": interactive,
            "contains_interactive": contains_interactive, "order": order,
            "aria_controls": aria_controls, "aria_haspopup": aria_haspopup}


def _nav_user_like() -> list[dict]:
    """demo `auth.js::mountTopbar` 的真实结构（`.nav-user` 下的三个兄弟）。

    `<span class="nu-who">`（可见·不可点） + `<button id="nu-avatar">`（可见·可点）
    + `<div id="nu-menu" style="display:none">`（隐藏·内含 3 个 button.nu-item）
    """
    return [
        _node("nu-who", "span", visible=True, order=0),
        _node("nu-avatar", "button", visible=True, interactive=True, order=1),
        _node("nu-menu", "div", visible=False, contains_interactive=True, order=2),
    ]


def test_picks_visible_trigger_before_hidden_menu():
    """判据 1（正向）：判出 `nu-avatar` 为 opener、`nu-menu` 为容器。"""
    got = pick_expandable_opener(_nav_user_like())
    assert got is not None, "demo 形态（可见 button + 紧随其后的隐藏菜单）必须被判出可展开"
    assert got["opener_key"] == "nu-avatar", f"opener 应为 nu-avatar，实际 {got}"
    assert got["container_key"] == "nu-menu", f"容器应为 nu-menu，实际 {got}"
    assert got["reason"] == "hidden-container-after-visible-trigger", f"结构判据的 reason 不对：{got}"


def test_aria_controls_wins_over_structure():
    """判据 2（正向）：显式 `aria-controls` 关联优先于结构判据，reason 可区分。"""
    sibs = [
        _node("btn-more", "button", visible=True, interactive=True, order=0),
        _node("btn-other", "button", visible=True, interactive=True, order=1),
        _node("menu", "div", visible=False, contains_interactive=True, order=2, aria_controls="btn-more"),
    ]
    got = pick_expandable_opener(sibs)
    assert got is not None and got["opener_key"] == "btn-more", f"应认 aria-controls 指向的 btn-more：{got}"
    assert got["reason"] == "aria-controls", f"显式声明应走 aria-controls 分支：{got}"


def test_negative_no_visible_trigger_returns_none():
    """判据 3（负向）：只有隐藏菜单、没有可见可点兄弟 -> None（不许乱点）。"""
    sibs = [
        _node("who", "span", visible=True, order=0),          # 可见但不可点
        _node("menu", "div", visible=False, contains_interactive=True, order=1),
    ]
    assert pick_expandable_opener(sibs) is None, "没有可见可点的触发器时必须放弃，绝不能猜一个去点"


def test_negative_visible_container_not_expandable():
    """判据 4（负向）：容器本身可见 -> 不是"待展开"，返回 None。"""
    sibs = [
        _node("btn", "button", visible=True, interactive=True, order=0),
        _node("panel", "div", visible=True, contains_interactive=True, order=1),
    ]
    assert pick_expandable_opener(sibs) is None, "可见容器不算可展开容器（它本来就能探到）"


def test_negative_hidden_container_without_interactive_returns_none():
    """判据 5（负向）：隐藏容器里没有交互控件（纯文案 div）-> None。"""
    sibs = [
        _node("btn", "button", visible=True, interactive=True, order=0),
        _node("tip", "div", visible=False, contains_interactive=False, order=1),
    ]
    assert pick_expandable_opener(sibs) is None, "隐藏的纯文案容器不是菜单，不该为它去点触发器"


def test_negative_trigger_after_container_returns_none():
    """判据 6（负向）：可见触发器在容器**之后** -> None（DOM 顺序不对，点了多半是别的东西）。"""
    sibs = [
        _node("menu", "div", visible=False, contains_interactive=True, order=0),
        _node("btn", "button", visible=True, interactive=True, order=1),
    ]
    assert pick_expandable_opener(sibs) is None, (
        "触发器必须位于隐藏容器之前（真实形态：先按钮后菜单）—— 顺序不对就别猜")
