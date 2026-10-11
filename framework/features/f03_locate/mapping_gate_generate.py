# -*- coding: utf-8 -*-
"""映射质量闸门（空 element / 未映射）

## 为什么住这里（B′ · 2026-10-11 拍定）

闸门**实现跟特性走**：这个闸门守卫的是「生成期 elementMap 映射完整性（特性3 分层定位）」，
所以它住在 `f03_locate/`，而不是全部堆进 `f09_gate`。
`f09_gate` 只提供统一契约（`Gate` / `GateResult` / 注册表 / 报告与退出码）。

## 口径

`check(**kw)` **委托现有实现**，不重写判定逻辑 —— 这一步是「搬家 + 统一契约」，
不是「改判定」（改判定会让历史判据与行为一起漂移，属于另一件事）。
拿不到必需输入时**如实返回**（entries 说明缺什么），绝不静默判过。
"""
from __future__ import annotations

from framework.features.f09_gate.gates import BLOCK, WARN, Gate, GateResult, register


class MappingGate(Gate):
    """映射质量闸门：elementMap 里 AI 用到的元素必须有 locator 落点。

    委托 `generator` 的未映射检查（若已抽出）；缺省时按传入的 `unmapped` 清单判定
    —— 调用方已经把"哪些名字没映射上"算出来了，这里只负责**统一形状 + 档位**。
    """

    name = "mapping"

    def check(self, **kw) -> GateResult:
        unmapped = list(kw.get("unmapped") or [])
        entries = [f"未映射到 locator：{x}" if not str(x).startswith(("未映射", "缺失"))
                   else str(x) for x in unmapped]
        return GateResult(gate=self.name, level=(BLOCK if entries else WARN), entries=entries)


register(MappingGate())
