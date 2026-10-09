# -*- coding: utf-8 -*-
"""特性2 · 语义校准不合格必须能**拦住产出**（V8.4.1）。

事故（Windows 实测 · AprilPark1012 2026-10-09）：
    AI 给「点右上角头像展开角色菜单」这一步选了控件 **`超@合同列表页`**
    （`超` 是登录后显示的用户名 —— 换个账号就不存在）；框架自己的校准器当场报警：

        [语义校准[!]] step3 「点击右上角头像打开角色切换菜单」vs 控件语义 重叠度 0.00 -> 疑似选错

    但它**只设了 notes + 打警告**，用例照样落盘 -> 第 2 轮实跑就崩在
        RuntimeError: 元素语义未找到: 超@合同列表页

口径：重叠度 **0.00**（完全不沾边）不是「可能选错」，是「一定选错」-> 必须能拦。
      既要拦住，也要**宁漏不误伤**：正常步骤（如「点搜索」vs 搜索按钮）不许被拦。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPLORER = REPO / "framework" / "tools" / "explore" / "explorer.py"


def _fn_src(name: str) -> str:
    src = EXPLORER.read_text(encoding="utf-8")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"explorer.py 里找不到 {name}()")


def test_mismatch_gate_collects_hard_mismatches():
    """必须有一个「把严重误选步骤收集出来」的入口（供重试闭环当失败原因）。"""
    src = EXPLORER.read_text(encoding="utf-8")
    assert "semantic_mismatch" in src or "严重误选" in src or "SEMANTIC_HARD_SIM" in src, (
        "没有「严重误选」这个档位 -> 0.00 重叠度和 0.29 一视同仁，都只警告不拦"
    )


def test_hard_threshold_is_lower_than_warn_threshold():
    """硬拦阈值必须**明显低于**警告阈值（宁漏不误伤：只有「完全不沾边」才拦）。"""
    src = EXPLORER.read_text(encoding="utf-8")
    ns: dict = {}
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("SEMANTIC_MIN_SIM") or s.startswith("SEMANTIC_HARD_SIM"):
            exec(compile(ast.parse(s), "<x>", "exec"), ns)   # noqa: S102
    assert "SEMANTIC_HARD_SIM" in ns, "没有 SEMANTIC_HARD_SIM 常量"
    assert ns["SEMANTIC_HARD_SIM"] < ns["SEMANTIC_MIN_SIM"], (
        f"硬拦阈值({ns.get('SEMANTIC_HARD_SIM')}) 必须 < 警告阈值({ns.get('SEMANTIC_MIN_SIM')})"
    )
    assert ns["SEMANTIC_HARD_SIM"] <= 0.05, (
        "硬拦阈值应贴着 0（实测事故是 0.00）—— 抬高了就会误拦正常步骤"
    )


def test_normal_steps_are_not_blocked():
    """反向自证：正常步骤的相似度不许被硬拦阈值碰到。"""
    body = _fn_src("_semantic_sim")
    ns: dict = {}
    exec(compile(ast.parse(body), "<x>", "exec"), ns)          # noqa: S102
    src = EXPLORER.read_text(encoding="utf-8")
    for helper in ("_to_char_set", "_ACTION_WORDS_STRIP"):
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == helper:
                        exec(compile(ast.Module(body=[node], type_ignores=[]), "<x>", "exec"), ns)   # noqa: S102
            elif isinstance(node, ast.FunctionDef) and node.name == helper:
                lines = src.splitlines()
                exec(compile(ast.parse("\n".join(lines[node.lineno - 1: node.end_lineno])), "<x>", "exec"), ns)   # noqa: S102
    sim = ns["_semantic_sim"]
    # 正常步骤：描述与控件语义明显沾边
    s1 = sim("点击搜索", "搜索")
    s2 = sim("保存新建订单", "保存")
    assert s1 > 0.05 and s2 > 0.05, f"正常步骤相似度太低会被误拦：搜索={s1} 保存={s2}"
