# -*- coding: utf-8 -*-
"""特性9 · 闸门**统一契约 + 全量注册表**契约（P25 片 0 · 判据先行，V8.5）

## 口径（AprilPark1012 2026-10-11 拍定：特性9 选 B′）

- 闸门**实现跟特性走**（哪个特性被守卫，闸门就住哪个特性目录）；
- 但**每个闸门必须实现统一 `Gate` 协议**，并**登记进 `core/gates.py` 的全量注册表**；
- `f09_gate` 只提供：统一契约 + 全量清单 + 报告/退出码。

这样同时满足「聚拢」（一处可见全部闸门 + 同一契约）与「特性自洽」。

## 契约面（新建能力，本判据锁契约名与行为）

`framework/features/f09_gate/gates.py`：

    @dataclass
    class GateResult:
        gate: str        # 闸门名（唯一）
        level: str       # "block"（拒产）/ "warn"（留痕）
        entries: list[str]   # 可读原因（给人看 = 喂 AI 重试也用这一份）

    GATE_REGISTRY: list[Gate]      # 全量注册表
    registered_gates() -> list[str]        # 已登记的闸门名
    verify_registry(expected: list[str]) -> list[str]   # 覆盖校验，返回问题清单（空 = 通过）

## 闸门归属（方案 §6.2，逐个落位）

| 闸门 | 目录 |
|---|---|
| AI 产出闸门（登录步骤/写死行数据/必填覆盖/语义误选） | features/f02_semantic/ai_output_gate_explore.py |
| 用例质量（假绿红线） | features/f02_semantic/case_quality_gate_generate.py |
| probe_pre 一致性（D9） | features/f02_semantic/probe_pre_gate_generate.py |
| 映射质量闸 | features/f03_locate/mapping_gate_generate.py |
| 歧义/行定位闸门 | features/f04_ambiguity/ambiguity_gate_generate.py |
| isValid 复核 | features/f03_locate/（probe 侧） |
| 数据组/悬空数据集 | features/f05_layers/data_gate_generate.py |
| 齐套校验（elementMap/录像/cases/scripts） | features/f09_gate/consistency_gate.py |

## 现状（片 0 基线，本判据**应当红**）

现在没有任何统一闸门契约：闸门散在 cli.py / generator.py / case_builder.py / explorer.py 四处，
结果靠**模块级全局**在模块间传递（cli.py:767/771/776/783 直读 explorer 私有名）。
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: 期望的闸门名（与方案 §6.2 归属表一一对应；新增闸门须同时加到这里 + 注册表）
EXPECTED_GATES = [
    "ai_output",        # f02：登录步骤 / 写死行数据 / 必填覆盖 / 语义误选
    "case_quality",     # f02：假绿红线
    "probe_pre",        # f02：用例与场景前置一致（D9）
    "mapping",          # f03：空 element / 未映射
    "ambiguity",        # f04：歧义 + 行定位
    "is_valid_rescan",  # f03：isValid 复核
    "data_sets",        # f05：数据组 / 悬空数据集
    "consistency",      # f09：齐套（elementMap / 录像 / cases / scripts）
]

#: 闸门模块落点（B′：实现跟特性走）
GATE_FILES = [
    "framework/features/f02_semantic/ai_output_gate_explore.py",
    "framework/features/f02_semantic/case_quality_gate_generate.py",
    "framework/features/f02_semantic/probe_pre_gate_generate.py",
    "framework/features/f03_locate/mapping_gate_generate.py",
    "framework/features/f04_ambiguity/ambiguity_gate_generate.py",
    "framework/features/f05_layers/data_gate_generate.py",
    "framework/features/f09_gate/consistency_gate.py",
]


def _module_exists(name: str) -> bool:
    """模块是否存在。

    [!] find_spec 在**父包都不存在**时会抛 ModuleNotFoundError（不是返回 None）——
    直接调用会把红态变成「import 崩」，那是不合格的红（P25 片 0 实测踩到）。
    """
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def _gates_mod():
    """拿 core.gates（不存在就 skip，避免 import 崩成不合格红态）。"""
    if not _module_exists("framework.features.f09_gate.gates"):
        pytest.skip("framework.features.f09_gate.gates 尚未实现（见 test_gate_contract_module_exists）")
    # [!] 必须走**运行期字符串导入**：写成静态 `from framework.features.f09_gate import gates` 会被
    #     test_import_targets（全仓 import 解析契约）抓到 -> 判据自己制造一条红（片 0 实测踩到）。
    import importlib
    return importlib.import_module("framework.features.f09_gate.gates")


def test_gate_contract_module_exists():
    """契约模块必须存在（统一契约 + 全量注册表的唯一住址）。"""
    assert _module_exists("framework.features.f09_gate.gates"), (
        "缺 framework/features/f09_gate/gates.py：统一 Gate 协议 + 全量注册表 + GateResult 应住这里；"
        "现状闸门散在 cli.py/generator.py/case_builder.py/explorer.py 四处，"
        "结果靠模块级全局传递（cli.py:767-786 直读 explorer 私有名）")


def test_gate_result_shape():
    """GateResult 必须有 gate / level / entries 三个字段。"""
    m = _gates_mod()
    cls = getattr(m, "GateResult", None)
    assert cls is not None, "缺 GateResult（闸门结果的唯一形状）"
    fields = set(getattr(cls, "__dataclass_fields__", {}) or {})
    assert {"gate", "level", "entries"} <= fields, f"GateResult 字段不全：{sorted(fields)}"


def test_registry_is_not_empty_and_entries_are_callable():
    """注册表非空，且每项都能 check()。"""
    m = _gates_mod()
    reg = list(getattr(m, "GATE_REGISTRY", []) or [])
    assert reg, "GATE_REGISTRY 为空：闸门必须登记（否则'一处可见全部闸门'无从谈起）"
    for g in reg:
        name = getattr(g, "name", None) or getattr(g, "gate", None)
        assert name, f"注册项缺名字：{g!r}"
        assert callable(getattr(g, "check", None)), f"闸门 {name!r} 没实现 check()"


def test_every_expected_gate_is_registered():
    """覆盖：方案里点名的闸门必须全部登记。"""
    m = _gates_mod()
    names = set()
    for g in list(getattr(m, "GATE_REGISTRY", []) or []):
        names.add(str(getattr(g, "name", None) or getattr(g, "gate", None) or ""))
    missing = [n for n in EXPECTED_GATES if n not in names]
    assert not missing, f"未登记的闸门：{missing}（已登记：{sorted(names)}）"


def test_registry_verifier_reports_missing():
    """负向自证：覆盖校验必须能报出'未登记'（否则校验器是空判据）。"""
    m = _gates_mod()
    fn = getattr(m, "verify_registry", None)
    assert callable(fn), "缺 verify_registry(expected) -> list[str]（覆盖校验的唯一入口）"
    problems = fn(["绝对不存在的闸门名"])
    assert problems, "verify_registry 对不存在的闸门必须报问题（负向自证）"


def test_gate_files_live_with_their_feature():
    """B′：闸门实现跟特性走（文件落点与方案 §6.2 一致）。"""
    missing = [f for f in GATE_FILES if not (REPO / f).exists()]
    assert not missing, (
        "闸门文件尚未按 B′ 落位：" + ", ".join(missing) +
        "（实现跟特性走，契约与注册表在 core/gates.py + f09_gate）")


def test_no_cross_module_private_globals_for_gate_results():
    """结果不许再靠模块级全局跨模块传递（现状 cli.py 直读 explorer 私有名）。"""
    src = (REPO / "framework" / "features" / "f10_cli" / "cli.py").read_text(encoding="utf-8", errors="replace")
    for bad in ("_HARDCODED_NOTES", "SEMANTIC_MISMATCH_NOTES",
                "_REQUIRED_COVERAGE_NOTES", "_ROW_SCOPE_NOTES"):
        assert bad not in src, (
            f"cli.py 仍在直读 explorer 的私有全局 {bad}："
            "闸门结果必须走 GateResult（显式返回），否则闸门一搬家/改名就静默失效")


def test_gate_module_has_no_browser_dependency():
    """闸门契约层不许依赖浏览器（保证一类判据秒级可跑、可被任何阶段复用）。"""
    m = _gates_mod()
    src = inspect.getsource(m)
    for bad in ("playwright", "sync_playwright"):
        assert bad not in src, f"core/gates.py 不该出现 {bad}（契约层保持无浏览器依赖）"
