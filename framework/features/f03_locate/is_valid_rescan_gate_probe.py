# -*- coding: utf-8 -*-
"""isValid 复核闸门（B′：实现跟特性走 —— 守卫「特性3 分层定位与控件识别」的探测侧）。

## 为什么单独一个文件

它守的是 **elementMap 里 `isValid=false` 的条目**（D3：保留条目、不参与映射、
排除计数要打印，但**不进提示词**）。判定口径归 elementMap，闸门只负责把它
变成统一的 `GateResult`。
"""
from __future__ import annotations

from framework.features.f09_gate.gates import BLOCK, WARN, Gate, GateResult, register


class IsValidRescanGate(Gate):
    """isValid 复核闸门：报出被排除映射的条目（数量 + 样例），供人核对。"""

    name = "is_valid_rescan"

    def check(self, **kw) -> GateResult:
        items = list(kw.get("items") or [])
        if not items:
            return GateResult(gate=self.name, level=WARN, entries=["未提供 items，本闸门未生效"])
        bad = [it for it in items
               if isinstance(it, dict) and it.get("isValid") is False]
        if not bad:
            # 无排除项 = 正常（不是问题），用 WARN 档并给出确认信息
            return GateResult(gate=self.name, level=WARN, entries=[])
        names = [str(it.get("semantic_name") or "?") for it in bad[:10]]
        return GateResult(
            gate=self.name, level=WARN,
            entries=[f"isValid=false 条目 {len(bad)} 条（保留但不参与映射，不进提示词）："
                     + ", ".join(names) + (" …" if len(bad) > 10 else "")])


register(IsValidRescanGate())
