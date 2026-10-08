# -*- coding: utf-8 -*-
"""特性3 · C 方案：现场探测的**范围**必须由「真正缺的语义名」决定（V8.3.7 性能治理 C）。

背景（2026-10-08 实测）：
    `_probe_declared_pages` 在**有缺失项**（`if live_probe or missing:`，第 1170 行）时进入，
    但进去之后两条路径都**无条件**跑：
      (1) 单页惯例探测（TARGET_URL + 弹窗）—— 注释写着「始终执行」；
      (2) 声明页探测 —— `if declared_pages:` 不看 `missing`。
    实测 7 页现场探测 **260.9s**（发票列表页一页 132s，占一半）——**其中大量是「缓存已经覆盖、
    本可不探」的页**。这正是 C 方案要省掉的**无用功**。

判据口径（AprilPark1012 2026-10-08 定的原则：能力与场景解耦、不写死）：
    本文件只测「**按缺口推导探测范围**」这条纯逻辑，不写死任何具体页面名/语义名 —— 页面名与
    语义名全部由判据现造。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "framework" / "tools" / "generate" / "generator.py"


def _fn_source(path: Path, name: str) -> str:
    """取某个模块里指定函数的源码（模块级函数）。"""
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"{path.name} 里找不到函数 {name}()")


def test_page_scope_helper_exists():
    """C：必须存在「按缺口推导探测范围」的纯函数（唯一口径，不许各处自己判断）。"""
    src = GENERATOR.read_text(encoding="utf-8")
    assert "_pages_to_probe" in src, (
        "generator.py 里缺少 `_pages_to_probe(...)` —— C 方案的页级筛选必须收敛成一个纯函数"
    )


def test_page_scope_single_only_when_bare_name_missing():
    """缺「裸名」时才需要单页惯例探测；缺的都是 `x@页名` 则不需要。"""
    from framework.tools.generate.generator import _pages_to_probe

    # 造两份缺口（不写死任何业务名）
    p0, u0 = "页面甲", "http://x/a"
    p1, u1 = "页面乙", "http://x/b"
    declared = [(p0, u0), (p1, u1)]

    need_single, pages = _pages_to_probe({"按钮A@" + p0}, declared)
    assert need_single is False, "缺口全是 `x@页名` 时，不该再跑单页惯例探测"
    assert pages == [(p0, u0)], f"只该探「缺口所属的页」，实际 {pages}"

    need_single2, pages2 = _pages_to_probe({"按钮A"}, declared)
    assert need_single2 is True, "缺口含裸名时必须跑单页惯例探测（裸名由单页补）"
    assert pages2 == [], "缺口全是裸名时，声明页探测不该被触发"


def test_page_scope_only_probes_pages_that_own_the_gap():
    """多个页、只有一个页有缺口 -> 只探那一页（这是省时的大头）。"""
    from framework.tools.generate.generator import _pages_to_probe

    declared = [(f"页{n}", f"http://x/{n}") for n in range(5)]
    gaps = {"控件@" + declared[2][0]}
    _, pages = _pages_to_probe(gaps, declared)
    assert pages == [declared[2]], f"只该探第 3 页，实际探了 {[p[0] for p in pages]}"


def test_page_scope_unknown_page_is_not_probed():
    """缺口指向的页不在声明的页面里 -> 不探（探了也补不上，纯浪费）。"""
    from framework.tools.generate.generator import _pages_to_probe

    declared = [("页面甲", "http://x/a")]
    _, pages = _pages_to_probe({"控件@不存在的页"}, declared)
    assert pages == [], f"缺口页不在声明列表里，不该探测，实际 {pages}"


def test_page_scope_keeps_order_and_dedupes():
    """多个缺口落在同一页 -> 该页只出现一次，且保持声明顺序（可复现）。"""
    from framework.tools.generate.generator import _pages_to_probe

    declared = [("甲", "http://x/a"), ("乙", "http://x/b"), ("丙", "http://x/c")]
    gaps = {"A@丙", "B@甲", "C@丙", "D@甲"}
    _, pages = _pages_to_probe(gaps, declared)
    assert pages == [("甲", "http://x/a"), ("丙", "http://x/c")], f"顺序/去重不对：{pages}"


def test_page_scope_empty_gaps_implies_nothing_to_probe():
    """没有缺口 -> 不探任何页（调用方据此整体跳过，不走现场探测）。"""
    from framework.tools.generate.generator import _pages_to_probe

    need_single, pages = _pages_to_probe(set(), [("甲", "http://x/a")])
    assert need_single is False and pages == [], "无缺口时不该产生任何探测动作"


def test_generator_uses_page_scope_helper():
    """接线判据：`generate_scripts` 里必须**用**这个纯函数决定探哪些页（不许自己 if 一遍）。"""
    body = _fn_source(GENERATOR, "generate_scripts")
    assert "_pages_to_probe(" in body, (
        "generate_scripts() 里没有调用 `_pages_to_probe(...)` —— C 的页级筛选没接上"
    )


def test_generator_no_longer_unconditionally_probes_all_declared_pages():
    """不许再出现「无条件探所有声明页」的写法（回退即红）。"""
    body = _fn_source(GENERATOR, "generate_scripts")
    assert "if declared_pages:\n" not in body.replace("            ", "            "), (
        "generate_scripts() 里仍有 `if declared_pages:` 无条件探所有声明页 —— C 方案被回退了"
    )
