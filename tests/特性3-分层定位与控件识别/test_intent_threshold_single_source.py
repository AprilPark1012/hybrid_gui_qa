# -*- coding: utf-8 -*-
"""一类判据：意图复验阈值**只有一个口径**（V8.9.7 · L11②）。

## 这道闸防的是什么

`func: locator_bridge_locate.py` 里有两个调质量门限的常量：

    INTENT_MIN_SIM = 0.15    # Tier1 意图复验
    TIER2_MINGAP   = 0.12    # Tier2 唯一性（最高分与次高分之差）

改动它们会直接决定「AI 写的语义名到底能不能落到控件上」——调宽了会出现
**错映射（点错控件）而用例照样绿**，属于假绿类风险。

真值（2026-11-05 清账）：`INTENT_MIN_SIM` 在**判定处被写成了字面量 0.15**：

    if _sim(hint, blob) < 0.15 and hint not in blob:      # ← 没引用常量

后果是「改常量只生效一半」：一处用新值、判定处还用旧值 —— 部分生效最难查。

## 口径

1. 判定处必须引用 `INTENT_MIN_SIM`，不许写字面量（源码契约 + AST）
2. **改常量必须真的生效**（行为判据：把常量改大，原本不降权的候选要被降权）
3. 阈值边界不逐个钉死（触发频率太低，用户 2026-11-05 裁定标可选）——
   但「常量是唯一来源」这一条必须钉死，否则边界语义无从谈起
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

SRC_PATH = REPO / "framework" / "features" / "f03_locate" / "locator_bridge_locate.py"


def _fn_src(name: str) -> str:
    src = SRC_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"找不到函数 {name} —— 判据要跟着代码结构更新")


# ---------------- (1) 源码契约：判定处用常量，不用字面量 ----------------

def test_intent_check_uses_constant_not_literal():
    """`_fingerprint_score` 里的意图判别必须引用 `INTENT_MIN_SIM`。

    为什么钉函数体而不是全文：`0.15` 在 `_T2_W`（text 权重）里是**合法**字面量，
    全文搜会把好代码判红 —— 判据要精确到「意图判别那一处」。
    """
    body = _fn_src("_fingerprint_score")
    assert "INTENT_MIN_SIM" in body, "意图判别没引用常量 INTENT_MIN_SIM（口径写了两份）"
    assert "< 0.15" not in body and "0.15 :" not in body, \
        "意图判别处还有裸字面量 0.15 —— 改常量不会生效"


def test_no_duplicated_intent_threshold_anywhere():
    """整个模块里参与**意图判定**的字面量对比只允许出现在常量定义处。"""
    src = SRC_PATH.read_text(encoding="utf-8")
    offenders = [f"第 {i} 行：{ln.strip()}"
                 for i, ln in enumerate(src.splitlines(), 1)
                 if "INTENT_MIN_SIM" not in ln and "_sim(" in ln and "0.15" in ln]
    assert not offenders, f"这些行用字面量 0.15 参与意图判定：{offenders}"


# ---------------- (2) 行为判据：改常量必须真的生效 ----------------

def _score(el, cand):
    from framework.features.f03_locate.locator_bridge_locate import _fingerprint_score
    return _fingerprint_score(el, cand)


def _el_with_hint(hint: str):
    from framework.features.f03_locate.element_map import ElementRef
    return ElementRef(semantic_name="t", page_hint=hint)


def test_changing_constant_changes_behavior(monkeypatch):
    """把 `INTENT_MIN_SIM` 改大 -> 原本「不降权」的候选必须被降权。

    这条是「唯一来源」的**行为**证据：只钉源码字符串，挡不住有人把常量算了却不用。
    """
    from framework.features.f03_locate import locator_bridge_locate as mod

    el = _el_with_hint("订单名称字段")           # 与候选不完全相同、也不是子串
    cand = {"name": "订单名称", "text": "订单名称", "label": "",
            "nearby_text": "", "container_heading": ""}

    monkeypatch.setattr(mod, "INTENT_MIN_SIM", 0.15)
    loose = _score(el, cand)
    monkeypatch.setattr(mod, "INTENT_MIN_SIM", 0.99)
    strict = _score(el, cand)

    assert strict < loose, (
        f"常量改大后行为没变（loose={loose} strict={strict}）—— "
        f"判定处大概没有真的用 INTENT_MIN_SIM")
    assert abs((loose - strict) - 0.20) < 1e-9, \
        f"降权幅度不是约定的 0.20（{loose - strict}）"


def test_mismatched_hint_is_penalized():
    """与意图完全不符的候选要被降权 0.20（保守只拦明显不符）。"""
    el = _el_with_hint("订单名称")
    good = _score(el, {"name": "订单名称", "text": "", "label": "",
                       "nearby_text": "", "container_heading": ""})
    bad = _score(el, {"name": "客户编号", "text": "", "label": "",
                      "nearby_text": "", "container_heading": ""})
    assert bad == good - 0.20, f"不符的候选降权不对：good={good} bad={bad}"
