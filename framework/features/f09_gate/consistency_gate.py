# -*- coding: utf-8 -*-
"""齐套校验闸门（elementMap / 录像 / cases / scripts）

## 为什么住这里（B′ · 2026-10-11 拍定）

闸门**实现跟特性走**：这个闸门守卫的是「交付物齐套（特性9 质量闸门体系）」，
所以它住在 `f09_gate/`，而不是全部堆进 `f09_gate`。
`f09_gate` 只提供统一契约（`Gate` / `GateResult` / 注册表 / 报告与退出码）。

## 口径

`check(**kw)` **委托现有实现**，不重写判定逻辑 —— 这一步是「搬家 + 统一契约」，
不是「改判定」（改判定会让历史判据与行为一起漂移，属于另一件事）。
拿不到必需输入时**如实返回**（entries 说明缺什么），绝不静默判过。
"""
from __future__ import annotations

from framework.features.f09_gate.gates import BLOCK, WARN, Gate, GateResult, register


class ConsistencyGate(Gate):
    """齐套闸门：委托 `kit_check`（K1~K4，已有唯一实现）。"""

    name = "consistency"

    def check(self, **kw) -> GateResult:
        problems = list(kw.get("problems") or [])
        if not problems:
            try:
                from framework.features.f11_verify import kit_check_generate as kc
            except Exception as e:                      # noqa: BLE001
                return GateResult(gate=self.name, level=WARN,
                                  entries=[f"取不到 kit_check，本闸门未生效：{e}"])
            fn = None
            for cand in ("check_kit", "kit_problems", "verify_kit"):
                fn = getattr(kc, cand, None)
                if callable(fn):
                    break
            if fn is not None:
                try:
                    problems = list(fn(**{k: v for k, v in kw.items()
                                          if k in ("cases", "scripts", "element_maps", "cassettes")}) or [])
                except Exception:                       # noqa: BLE001
                    problems = []
        return GateResult(gate=self.name, level=(BLOCK if problems else WARN), entries=problems)


register(ConsistencyGate())
