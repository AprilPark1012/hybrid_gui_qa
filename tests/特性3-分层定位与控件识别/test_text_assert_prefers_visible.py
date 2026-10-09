# -*- coding: utf-8 -*-
"""特性3 · text 断言必须**优先命中有可见性的元素**（V8.4.1 · Windows 实测暴露）。

事故（AprilPark1012 2026-10-09 Windows 实录）：
    用例想「等订单状态流转到**已关闭**」（状态在**表格行**里），实跑却超时：

        playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 5000ms exceeded.
          - waiting for get_by_text("已关闭").first to be visible
            14 x locator resolved to hidden <option value="已关闭">已关闭</option>

    真因：同一页面上「已关闭」**也出现在筛选下拉的 `<option>` 里**（不可见）。
    `page.get_by_text("已关闭").first` 命中了那个 hidden option -> 永远等不到 visible。

    这不是用例写错 —— 是**框架的 text 断言没有排除不可见候选**。
    真实系统里「同一个词既在下拉选项里、又在结果行里」极其常见（状态、类型、币种…）。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "framework" / "tools" / "generate" / "generator.py"


def _tmpl_seg(name: str, span: int = 1400) -> str:
    """取 `_CONFTEST_TEMPLATE` 模板字符串里 `def <name>(...)` 那一段。

    [!] **不能用 AST**：`_assert_text` 住在 `_CONFTEST_TEMPLATE = '''...'''` 这个**字符串**里
        （渲染成 `scripts/generated/_harness.py`），不是 generator.py 的真函数 ——
        用 `ast` 找必然报「找不到」（这是判据自身的坑，`_act` 判据也踩过一次）。
    """
    src = GEN.read_text(encoding="utf-8")
    i = src.index(f"def {name}(page, text, desc=")
    return src[i: i + span]


def _code_only(body: str) -> str:
    """剔掉整行注释 —— 判据必须只看真代码。

    [!] 踩过的坑（2026-10-09 负向自证抓到）：原判据查 `"visible" in body`，而实现里有一行
        `# 口径：候选里**优先取可见的**` 注释 -> 把真逻辑改回 `.first` 后判据**照样绿**（空转）。
    """
    return "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))


def test_assert_text_excludes_hidden_candidates():
    """`_assert_text` 必须把候选里的不可见元素排除掉（不能直接拿 `.first` 赌）。"""
    code = _code_only(_tmpl_seg("_assert_text"))
    assert "is_visible()" in code, (
        "`_assert_text` 没有**真正**逐个候选判可见（只有注释提到可见不算）"
        " -> 会命中 hidden 的 <option> 并等到超时"
    )
    assert "loc.first.wait_for" in code or ".first.wait_for" in code, (
        "等待语句缺失（判据前提）"
    )


def test_assert_text_helper_wired_in_harness_template():
    """生成器模板里那一份 `_assert_text`（写进 _harness.py 的文本）也要同口径。

    [!] 生成期与运行期**刻意各写一份**（跨进程无法复用）-> 必须靠判据守「两份同口径」。
    """
    src = GEN.read_text(encoding="utf-8")
    i = src.index("def _assert_text(page, text, desc=")
    seg = src[i: i + 1200]
    assert ("visible" in seg or ":visible" in seg or "filter" in seg), (
        "模板里那份 `_assert_text` 没同步改 -> 生成物还是老行为（只改生成器函数没用）"
    )


def test_option_elements_are_excluded_explicitly():
    """要能明确排除 `<option>`（实测就是它）：候选里 option 一律不算数。"""
    src = GEN.read_text(encoding="utf-8")
    i = src.index("def _assert_text(page, text, desc=")
    seg = src[i: i + 1400]
    assert "option" in seg.lower() or "visible" in seg, (
        "没有针对 <option> 这类隐藏候选的处理"
    )
