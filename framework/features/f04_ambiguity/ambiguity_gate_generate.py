# -*- coding: utf-8 -*-
"""歧义 / 行定位闸门

## 为什么住这里（B′ · 2026-10-11 拍定）

闸门**实现跟特性走**：这个闸门守卫的是「同名同区域控件被选错的风险（特性4 选错控件兜底）」，
所以它住在 `f04_ambiguity/`，而不是全部堆进 `f09_gate`。
`f09_gate` 只提供统一契约（`Gate` / `GateResult` / 注册表 / 报告与退出码）。

## 口径

`check(**kw)` **委托现有实现**，不重写判定逻辑 —— 这一步是「搬家 + 统一契约」，
不是「改判定」（改判定会让历史判据与行为一起漂移，属于另一件事）。
拿不到必需输入时**如实返回**（entries 说明缺什么），绝不静默判过。
"""
from __future__ import annotations

from framework.features.f09_gate.gates import BLOCK, WARN, Gate, GateResult, register


class AmbiguityGate(Gate):
    """歧义闸门：委托 `element_map.row_scope_violation`（已有唯一入口）。"""

    name = "ambiguity"

    def check(self, **kw) -> GateResult:
        """`steps` + `multi_match`（名字 -> 重复个数）-> 逐条判定。

        `row_scope_violation(step, multi_match)` 是既有唯一入口，这里只做批量 + 统一形状。
        """
        steps = list(kw.get("steps") or [])
        mmap = dict(kw.get("multi_match") or {})
        if not steps:
            return GateResult(gate=self.name, level=WARN, entries=["未提供 steps，本闸门未生效"])
        try:
            from framework.features.f03_locate.element_map import row_scope_violation
            from framework.features.f03_locate.element_map import step_get as _sg
        except Exception as e:                          # noqa: BLE001
            return GateResult(gate=self.name, level=WARN,
                              entries=[f"取不到 element_map，本闸门未生效：{e}"])
        entries: list[str] = []
        for st in steps:
            name = ""
            try:
                ref = _sg(st, "element")
                name = (ref.get("semantic_name") if isinstance(ref, dict)
                        else getattr(ref, "semantic_name", "")) or ""
            except Exception:                           # noqa: BLE001
                name = ""
            n = mmap.get(name)
            why = row_scope_violation(st, n)
            if why:
                entries.append(why)
        return GateResult(gate=self.name, level=(BLOCK if entries else WARN), entries=entries)


register(AmbiguityGate())
