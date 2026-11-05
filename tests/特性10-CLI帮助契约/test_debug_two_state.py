# -*- coding: utf-8 -*-
"""一类判据：`--debug` **两态**（有/无图形显示）行为（V8.9.7 · L11③）。

## 这道闸防的是什么

用户定的工程准则原话：

> **开关「开了就要好用」**：受限环境降级为等效可用（无 DISPLAY → 无头 + 录屏/截图），不报错退出

`--debug` 就是这个开关。它的两态：

| 本机 | 应该发生什么 |
|---|---|
| 有图形显示（Windows 桌面 / 带 X 的 Linux） | `HYBRID_HEADED=1` → **弹出 Chromium 窗口**，肉眼跟步 |
| 没有图形显示（CI / 容器 / 无 DISPLAY） | `HYBRID_VIDEO=1` + `HYBRID_SHOTS=1` → **录成 webm + 每步一张 PNG** |

真值（2026-11-05 清账）：这套逻辑**已经实现**，但**内联在 `run()` 里十来行**，
要测只能起真浏览器（二类），于是**从来没有自动化判据**。

改坏的症状极其隐蔽：**Windows（有屏）上一切正常，无屏机器静默退化成没截图没录像** ——
等到要排查时才发现"什么都没留下"。而这正是「开关开了没好用」最典型的形态。

## 口径

1. 两态决策只有**一个入口** `debug_env_plan()`（纯函数）—— `run()` 不许再内联赋值
2. 有屏**只**设 `HYBRID_HEADED`；无屏**必须**设 `HYBRID_VIDEO` + `HYBRID_SHOTS`
3. 两态都要**给人话说明**（有屏说"弹窗"，无屏说"录制/截图"）——
   开关开了要让人知道"为什么是这样"
4. 不开 `--debug` 时**一个环境变量都不许设**（不许顺手把调试产物打开）
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CLI = REPO / "framework" / "features" / "f10_cli" / "cli.py"
_KEYS = ("HYBRID_HEADED", "HYBRID_VIDEO", "HYBRID_SHOTS")


def _plan(**kw):
    from framework.features.f10_cli.cli import debug_env_plan
    return debug_env_plan(**kw)


# ---------------- (1) 有屏：只开窗 ----------------

def test_with_display_opens_window_only():
    p = _plan(debug=True, has_display=True, workers=3)
    assert p["env"].get("HYBRID_HEADED") == "1", f"有屏没开窗：{p['env']}"
    assert "HYBRID_VIDEO" not in p["env"], "有屏不该录制（会白占磁盘 + 拖慢）"
    assert "HYBRID_SHOTS" not in p["env"], "有屏已有窗口，不必每步截图"
    assert p["workers"] == 1, "调试模式必须把并发降到 1（多浏览器看不清）"
    assert p["slowmo"] == 200, "调试模式默认放慢 200ms"
    assert any("窗口" in ln for ln in p["lines"]), "没告诉用户「会弹出窗口」"
    assert any("并发" in ln for ln in p["lines"]), "并发被改了却没说"


# ---------------- (2) 无屏：降级成录制 + 截图 ----------------

def test_without_display_falls_back_to_recording():
    """无图形显示时必须降级成「录屏 + 逐步截图」—— 这是「开关开了就要好用」的硬要求。"""
    p = _plan(debug=True, has_display=False)
    assert p["env"].get("HYBRID_VIDEO") == "1", f"无屏没录像：{p['env']}"
    assert p["env"].get("HYBRID_SHOTS") == "1", f"无屏没截图：{p['env']}"
    assert "HYBRID_HEADED" not in p["env"], "无屏还想开窗（会直接起不来）"
    assert p["workers"] == 1
    joined = " ".join(p["lines"])
    assert "录" in joined and "截图" in joined, f"没告诉用户「降级成录制」：{p['lines']}"
    assert "DISPLAY" in joined or "图形显示" in joined, "没说清为什么降级"


# ---------------- (3) 不开 --debug：一个变量都不许设 ----------------

def test_debug_off_sets_nothing():
    p = _plan(debug=False, has_display=True)
    assert p["env"] == {}, f"没开调试却设了环境变量：{p['env']}"
    assert p["lines"] == []
    assert p["workers"] == 1 and p["slowmo"] == 0


# ---------------- (4) 显式 --slowmo 不被覆盖 ----------------

def test_explicit_slowmo_is_respected():
    p = _plan(debug=True, has_display=True, slowmo=500)
    assert p["slowmo"] == 500, "用户显式给了 --slowmo 却被默认值覆盖"
    assert not any("默认放慢" in ln for ln in p["lines"]), "显式给值时不该再说「默认放慢」"


# ---------------- (5) 源码契约：两态赋值只允许在唯一入口里 ----------------

def test_env_assignments_only_in_single_entry():
    """`HYBRID_HEADED/VIDEO/SHOTS` 的**赋值**只允许出现在 `debug_env_plan` 里。

    为什么钉：内联赋值是这次问题的根源（逻辑散在 `run()` 里 -> 无法测 -> 没人守）。
    将来有人"顺手"又在别处写一行 `os.environ["HYBRID_VIDEO"]="1"`，这条当场红。
    """
    src = CLI.read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad: list[str] = []

    class _V(ast.NodeVisitor):
        def __init__(self):
            self.fn = "<module>"

        def visit_FunctionDef(self, node):            # noqa: N802
            prev, self.fn = self.fn, node.name
            self.generic_visit(node)
            self.fn = prev

        def visit_Assign(self, node):                 # noqa: N802
            for tgt in node.targets:
                key = None
                if isinstance(tgt, ast.Subscript) and isinstance(tgt.slice, ast.Constant):
                    key = tgt.slice.value
                if key in _KEYS and self.fn != "debug_env_plan":
                    bad.append(f"{self.fn} 第 {node.lineno} 行给 {key} 赋值")
            self.generic_visit(node)

    _V().visit(tree)
    assert not bad, f"这些地方绕过了唯一入口 debug_env_plan：{bad}"
