# -*- coding: utf-8 -*-
"""probe_pre 一致性闸门（D9）

## 为什么住这里（B′ · 2026-10-11 拍定）

闸门**实现跟特性走**：这个闸门守卫的是「用例级与场景级探测前置的一致性（特性2）」，
所以它住在 `f02_semantic/`，而不是全部堆进 `f09_gate`。
`f09_gate` 只提供统一契约（`Gate` / `GateResult` / 注册表 / 报告与退出码）。

## 口径

`check(**kw)` **委托现有实现**，不重写判定逻辑 —— 这一步是「搬家 + 统一契约」，
不是「改判定」（改判定会让历史判据与行为一起漂移，属于另一件事）。
拿不到必需输入时**如实返回**（entries 说明缺什么），绝不静默判过。
"""
from __future__ import annotations

from framework.features.f09_gate.gates import BLOCK, WARN, Gate, GateResult, register


class ProbePreGate(Gate):
    """probe_pre 一致性闸门：委托 `scenario.probe_pre_conflicts`（已有唯一实现）。"""

    name = "probe_pre"

    def check(self, **kw) -> GateResult:
        case, scenario = kw.get("case"), kw.get("scenario")
        if case is None:
            return GateResult(gate=self.name, level=WARN, entries=["未提供 case，本闸门未生效"])
        try:
            from framework.features.f02_semantic.scenario_generate import probe_pre_conflicts
        except Exception as e:                          # noqa: BLE001
            return GateResult(gate=self.name, level=WARN,
                              entries=[f"取不到 scenario 模块，本闸门未生效：{e}"])
        problems = list(probe_pre_conflicts(case, scenario) or [])
        return GateResult(gate=self.name, level=(BLOCK if problems else WARN), entries=problems)


register(ProbePreGate())
