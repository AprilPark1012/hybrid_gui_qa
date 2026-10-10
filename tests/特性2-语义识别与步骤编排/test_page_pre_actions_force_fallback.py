# -*- coding: utf-8 -*-
"""特性2 · `pages[].pre` 前置动作必须带 **force 回退**（2026-10-10 干净环境实测）。

事故：场景给「订单详情页」声明了 `pre: ["编辑", "新增行"]`，探测期两条都失败：
    [explore] [!] [订单详情页] 前置动作「编辑」执行失败（TimeoutError: Locator.click: Timeout 5000ms exceeded）
    [explore] [!] [订单详情页] 前置动作「新增行」执行失败（TimeoutError: ...）
真因：探测期的**权限上下文与执行期不同** —— 场景里"切角色"是后面的一步，
      而探测在它之前跑 => 「编辑」此时是 `aria-disabled` => Playwright 常规点击被直接拒绝。
      本 demo 的口径是「置灰但仍可点、点了弹提示」（verify_role_switch_click.py 判据 1c 已钉死），
      => 探测期 force 一次是安全的（真有权限限制时应用只会弹提示、状态不变）。

[!] 同一症状在**两条互不相干的机制**上都出现过（声明的 pre 与新增的编辑态补探），
    所以这条判据钉的是**共性**：探测期点控件必须对"置灰"有韧性。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO = Path(__file__).resolve().parents[2]
EXPLORER = REPO / "framework" / "tools" / "explore" / "explorer.py"


def _code_only(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))


def _pre_actions_body() -> str:
    src = EXPLORER.read_text(encoding="utf-8")
    i = src.index("def _run_pre_actions(")
    j = src.index("\ndef ", i + 1)
    return src[i:j]


def test_pre_actions_have_force_fallback():
    code = _code_only(_pre_actions_body())
    assert "force=True" in code, (
        "`_run_pre_actions` 没有 force 回退 -> 探测期遇到置灰(aria-disabled)控件会直接失败，"
        "前置动作等于白声明（2026-10-10 实测两次）"
    )
    assert "except" in code, "没有捕获常规点击失败 -> force 回退无从触发"


def test_pre_actions_keep_bounded_and_no_guessing():
    """防跑偏：仍必须有界、且找不到就如实告警（不许自己换控件猜着点）。"""
    code = _code_only(_pre_actions_body())
    assert "per_step_ms" in code, "有界超时丢了"
    assert "没找到" in code, "找不到控件时没有如实告警（会静默跳过）"
