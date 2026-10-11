# -*- coding: utf-8 -*-
"""AI 产出闸门（登录步骤 / 写死行数据 / 必填覆盖 / 语义误选）

## 为什么住这里（B′ · 2026-10-11 拍定）

闸门**实现跟特性走**：这个闸门守卫的是「AI 探索产出（特性2 语义识别与步骤编排）的探索侧」，
所以它住在 `f02_semantic/`，而不是全部堆进 `f09_gate`。
`f09_gate` 只提供统一契约（`Gate` / `GateResult` / 注册表 / 报告与退出码）。

## 口径

`check(**kw)` **委托现有实现**，不重写判定逻辑 —— 这一步是「搬家 + 统一契约」，
不是「改判定」（改判定会让历史判据与行为一起漂移，属于另一件事）。
拿不到必需输入时**如实返回**（entries 说明缺什么），绝不静默判过。
"""
from __future__ import annotations

from framework.features.f09_gate.gates import BLOCK, WARN, Gate, GateResult, register


class AiOutputGate(Gate):
    """AI 产出闸门：把 explorer 收集到的四类问题汇总成统一 GateResult。

    这四类原来靠**模块级全局**在模块间传递（`explorer._HARDCODED_NOTES` /
    `SEMANTIC_MISMATCH_NOTES` / `_REQUIRED_COVERAGE_NOTES` / `_ROW_SCOPE_NOTES`），
    cli 用 `getattr` 直读 —— 上游没填、改名、或闸门搬家，就**静默失效**（读不到当没问题）。
    现在统一走 `GateResult`（显式返回），cli 只认这一个形状。
    """

    name = "ai_output"

    #: 四类问题的（私有全局名, 人类可读标签）—— 保留原名以便**只搬家不改行为**
    SOURCES = (
        ("_HARDCODED_NOTES", "AI 用了写死的行数据（应为行定位）"),
        ("SEMANTIC_MISMATCH_NOTES", "语义误选（AI 选的控件与步骤语义不符）"),
        ("_REQUIRED_COVERAGE_NOTES", "场景点名的必填项 AI 没编排"),
        ("_ROW_SCOPE_NOTES", "行内控件缺行定位（多匹配）"),
    )

    def check(self, **kw) -> GateResult:
        """从 explorer 模块读四类清单 -> GateResult。

        `explorer` 可由调用方注入（便于判据不依赖真实探索）；缺省时按运行期模块取。
        """
        expl = kw.get("explorer")
        if expl is None:
            try:
                from framework.features.f02_semantic import explorer_explore as expl
            except Exception as e:                      # noqa: BLE001
                return GateResult(gate=self.name, level=WARN,
                                  entries=[f"取不到 explorer 模块，本闸门未生效：{e}"])
        entries: list[str] = []
        for attr, label in self.SOURCES:
            got = list(getattr(expl, attr, None) or [])
            for x in got:
                entries.append(f"[{label}] {x}")
        return GateResult(gate=self.name, level=(BLOCK if entries else WARN), entries=entries)


register(AiOutputGate())
