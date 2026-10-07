"""护栏：用例脚本 import 的 helper 必须覆盖模板里**可能被渲染出**的 helper（一类，秒级）。

真值 2026-09-30（P22 批 5）：
  `wait_text` 断言渲染出 `_assert_wait_text(...)`，但用例头部的 `from _harness import (...)` 是
  **硬编码列表** ⇒ 生成物一跑就是 `NameError: name '_assert_wait_text' is not defined`。
  模板里连「漏一个就是 NameError」的警告都写着，仍然漏了 —— 所以把这条变成红灯，而不是靠记性。

口径：凡在模板源码里以调用形式出现（非 `def`）的 `_assert_*`，都必须在 import 列表里。
"""
from __future__ import annotations

import re
from pathlib import Path

import framework.tools.generate.generator as gen

SRC = Path(gen.__file__).read_text(encoding="utf-8")


def _imported_from_harness() -> set[str]:
    """解析用例头部的 `from _harness import (...)` 列表（含跨行）。"""
    m = re.search(r"from _harness import \((.*?)\)\n# P16", SRC, re.S)
    assert m, "找不到用例头部的 import 列表（模板结构变了？判据需同步）"
    body = re.sub(r"#[^\n]*", "", m.group(1))          # 去掉行内注释
    return {n.strip() for n in re.split(r"[,\n]+", body) if n.strip()}


def _rendered_assert_helpers() -> set[str]:
    """模板里以**调用**形式出现的 `_assert_*`（排除 def 定义行）。"""
    names: set[str] = set()
    for m in re.finditer(r"(_assert_[a-z_]+)\(", SRC):
        head = SRC[max(0, m.start() - 4):m.start()]
        if head.endswith("def "):
            continue
        names.add(m.group(1))
    return names


def test_every_rendered_assert_helper_is_imported():
    rendered = _rendered_assert_helpers()
    assert rendered, "没扫到任何 _assert_* 调用 —— 正则或模板结构变了，判据要修（别让它静默变空）"
    missing = sorted(rendered - _imported_from_harness())
    assert not missing, (
        f"这些 helper 会被渲染进用例、却没在 `from _harness import (...)` 里：{missing}"
        f"⇒ 生成物运行必然 NameError")
