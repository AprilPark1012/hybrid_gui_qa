# -*- coding: utf-8 -*-
"""闸门统一契约（特性9 · B′ 落地 · P25 片 1 骨架）。

## 口径（AprilPark1012 2026-10-11 拍定：特性9 选 B′）

- 闸门**实现跟特性走** —— 哪个特性被守卫，闸门就住哪个特性目录
  （例：歧义闸门住 `features/f04_ambiguity/`，映射闸住 `features/f03_locate/`）；
- 但**每个闸门必须实现本模块的 `Gate` 契约**，并**登记进 `GATE_REGISTRY`**；
- `features/f09_gate/` 只提供：**统一契约 + 全量清单 + 报告与退出码**。

这样同时满足「聚拢」（一处可见全部闸门 + 同一契约）与「特性自洽」。

## 为什么必须收敛（现状的反面）

现在闸门散在四处（`cli.py` / `generator.py` / `case_builder.py` / `explorer.py`），
结果靠**模块级全局**在模块之间传递（`cli.py:767-786` 用 `getattr` 直读 explorer 的私有清单）
—— 闸门一搬家、改名、或者上游没填，就**静默失效**（读不到 -> 当成"没问题"）。

## 用法（唯一入口）

    from framework.features.f09_gate.gates import Gate, GateResult, GATE_REGISTRY, verify_registry

    class MappingGate(Gate):
        name = "mapping"
        def check(self, **kw) -> GateResult: ...

    # 登记在闸门自己的模块里（import 即登记），f09 只做汇总与报告。

[!] 本模块**不许依赖浏览器**（判据守着）：闸门契约层要能在秒级一类判据里跑，
    也要能被任意阶段复用（探测期/生成期/执行期）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["BLOCK", "WARN", "GateResult", "Gate", "GATE_REGISTRY",
           "register", "registered_gates", "verify_registry", "run_gates"]

#: 闸门结果的两种档位：block = 拒产（exit 2）；warn = 只留痕
BLOCK = "block"
WARN = "warn"


@dataclass
class GateResult:
    """一次闸门判定的结果 —— **唯一形状**（人看的、喂 AI 重试的，都是这一份）。

    gate    闸门名（唯一，与注册表登记名一致）
    level   "block" / "warn"
    entries 可读原因（每条一句话；空列表 = 通过）
    """

    gate: str
    level: str = WARN
    entries: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.entries

    @property
    def blocked(self) -> bool:
        return self.level == BLOCK and bool(self.entries)

    def as_text(self) -> str:
        return "\n".join(f"[{self.gate}] {e}" for e in self.entries)


class Gate:
    """闸门基类（契约面）。

    子类必须给 `name`，并实现 `check(**kw) -> GateResult`。
    [!] 不强制继承：判据只认「有 name 且 check 可调用」（鸭子类型），
        这样闸门实现可以放在任何特性目录里而不必反向依赖本模块的实现细节。
    """

    name: str = ""

    def check(self, **kw) -> GateResult:          # pragma: no cover - 抽象
        raise NotImplementedError(f"闸门 {self.name!r} 必须实现 check()")


#: 全量注册表（登记点在各闸门自己的模块里；此处只做汇总）
GATE_REGISTRY: list = []


def register(gate) -> None:
    """登记一个闸门（幂等：同名只保留一个，重复登记**报错**而不是静默覆盖）。

    为什么重复登记要报错：同名闸门覆盖 = 后登记的那个悄悄顶掉前一个，
    闸门"消失"却没有任何信号（本项目吃过同类静默失效的亏）。
    """
    name = str(getattr(gate, "name", "") or "")
    if not name:
        raise ValueError(f"闸门缺 name，无法登记：{gate!r}")
    if not callable(getattr(gate, "check", None)):
        raise ValueError(f"闸门 {name!r} 没实现 check()，不许登记")
    for g in GATE_REGISTRY:
        if getattr(g, "name", None) == name:
            if g is gate:
                return                                  # 同一实例重复登记：幂等
            raise ValueError(f"闸门名 {name!r} 已被另一个实例登记（不许静默覆盖）")
    GATE_REGISTRY.append(gate)


def registered_gates() -> list:
    """已登记的闸门名（按登记顺序）。"""
    return [str(getattr(g, "name", "")) for g in GATE_REGISTRY]


def verify_registry(expected) -> list:
    """覆盖校验：`expected` 里的闸门是否都已登记。返回**问题清单**（空 = 通过）。

    用途：判据用它守「方案点名的闸门一个都不能漏」；
    也能被 f09 在启动时自省（"我认得几个闸门、缺哪些"）。
    """
    have = set(registered_gates())
    problems = [f"未登记的闸门：{n}" for n in expected if n not in have]
    for n in sorted(have - set(expected)):
        problems.append(f"登记了但不在期望清单里的闸门（清单该更新了）：{n}")
    return problems


def run_gates(gates=None, **kw) -> list:
    """按登记顺序跑闸门，返回结果清单（**只判定、不打印、不退出**）。

    调用方（f09 报告层 / cli）负责：打印 + 按 level 决定退出码。
    """
    out = []
    for g in (GATE_REGISTRY if gates is None else gates):
        res = g.check(**kw)
        if isinstance(res, GateResult):
            out.append(res)
    return out
