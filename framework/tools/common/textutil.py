# -*- coding: utf-8 -*-
"""文本归一化的**唯一实现**（2026-09-24 事故②的修复）。

背景：demo（以及真实系统）里 `<option>`／按钮的文本可能带**换行与多余空白**，
形如 `"请选择管理单元\n0021\n0451\n1031"`。浏览器在计算 **accessible name** 时会把
连续空白压成一个空格，而 Playwright 的 `get_by_role(name=…)`／`get_by_label(…)` 匹配
走的正是 accessible name ⇒ **needle 不归一化就永远匹配不到**。

实测证据：`RuntimeError: 元素定位失败且自愈未成功: 请选择_0021_0451_1031`

⚠️ 只用于**非精确匹配**的 name/label：
   · `get_by_role(..., name=…)` / `get_by_label(…)`  → 归一化 ✔
   · `get_by_text(..., exact=True)` / `get_by_placeholder(…)` / xpath 的 `normalize-space()` 之外
     的精确比对 → **保持原样** ✘（归一化会改变语义）
"""
from __future__ import annotations


def collapse_ws(value) -> str:
    """把任意文本的空白序列（空格/换行/制表符/全角空格等）压成单个半角空格。"""
    return " ".join(str("" if value is None else value).split())
