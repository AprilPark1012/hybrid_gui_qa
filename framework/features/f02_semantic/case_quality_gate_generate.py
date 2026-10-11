# -*- coding: utf-8 -*-
"""用例质量闸门（假绿红线）

## 为什么住这里（B′ · 2026-10-11 拍定）

闸门**实现跟特性走**：这个闸门守卫的是「生成期用例质量（特性2）」，
所以它住在 `f02_semantic/`，而不是全部堆进 `f09_gate`。
`f09_gate` 只提供统一契约（`Gate` / `GateResult` / 注册表 / 报告与退出码）。

## 口径

`check(**kw)` **委托现有实现**，不重写判定逻辑 —— 这一步是「搬家 + 统一契约」，
不是「改判定」（改判定会让历史判据与行为一起漂移，属于另一件事）。
拿不到必需输入时**如实返回**（entries 说明缺什么），绝不静默判过。
"""
from __future__ import annotations

from framework.features.f09_gate.gates import BLOCK, WARN, Gate, GateResult, register


class CaseQualityGate(Gate):
    """用例质量闸门：自造片段/假绿等红线。委托 `case_builder` 现有实现。"""

    name = "case_quality"

    def check(self, **kw) -> GateResult:
        """`case` 给出要检查的用例；结果委托 `case_builder.check_case_quality`（若存在）。

        [!] 找不到受托函数时**如实说明**（WARN + entries），不静默判过。
        """
        case = kw.get("case")
        if case is None:
            return GateResult(gate=self.name, level=WARN, entries=["未提供 case，本闸门未生效"])
        try:
            from framework.features.f02_semantic import case_builder_generate as cb
        except Exception as e:                          # noqa: BLE001
            return GateResult(gate=self.name, level=WARN,
                              entries=[f"取不到 case_builder，本闸门未生效：{e}"])
        fn = None
        for cand in ("check_case_quality", "case_quality_problems", "quality_problems"):
            fn = getattr(cb, cand, None)
            if callable(fn):
                break
        if fn is None:
            return GateResult(gate=self.name, level=WARN,
                              entries=["case_builder 里未找到质量判定入口（待收口到唯一入口）"])
        try:
            problems = list(fn(case) or [])
        except TypeError:
            problems = list(fn(case=case) or [])
        return GateResult(gate=self.name, level=(BLOCK if problems else WARN), entries=problems)


register(CaseQualityGate())
