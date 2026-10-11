# -*- coding: utf-8 -*-
"""数据组闸门（数据组 / 悬空数据集）

## 为什么住这里（B′ · 2026-10-11 拍定）

闸门**实现跟特性走**：这个闸门守卫的是「用例-脚本-数据三层分离的完整性（特性5）」，
所以它住在 `f05_layers/`，而不是全部堆进 `f09_gate`。
`f09_gate` 只提供统一契约（`Gate` / `GateResult` / 注册表 / 报告与退出码）。

## 口径

`check(**kw)` **委托现有实现**，不重写判定逻辑 —— 这一步是「搬家 + 统一契约」，
不是「改判定」（改判定会让历史判据与行为一起漂移，属于另一件事）。
拿不到必需输入时**如实返回**（entries 说明缺什么），绝不静默判过。
"""
from __future__ import annotations

from framework.features.f09_gate.gates import BLOCK, WARN, Gate, GateResult, register


class DataSetsGate(Gate):
    """数据组闸门：悬空/缺失数据集。

    委托 `data_driven` 现有检查（若已抽出）；缺省按传入的 `problems` 清单判定。
    """

    name = "data_sets"

    def check(self, **kw) -> GateResult:
        problems = list(kw.get("problems") or [])
        if not problems:
            try:
                from framework.features.f05_layers import data_driven_generate as dd
            except Exception:                           # noqa: BLE001
                return GateResult(gate=self.name, level=WARN,
                                  entries=["取不到 data_driven，本闸门未生效"])
            fn = getattr(dd, "dangling_data_sets", None)
            if callable(fn):
                try:
                    problems = list(fn(kw.get("cases") or []) or [])
                except Exception:                       # noqa: BLE001
                    problems = []
        return GateResult(gate=self.name, level=(BLOCK if problems else WARN), entries=problems)


register(DataSetsGate())
