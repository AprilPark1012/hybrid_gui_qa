# -*- coding: utf-8 -*-
"""特性2 · explore 侧收集到的**产出缺陷**必须接进 L1 校验（V8.4.2）。

事故（2026-10-09）：
    V8.4.1 加了两个收集器 ——
      · `_HARDCODED_NOTES`        —— 写死了表格行数据的具体值
      · `SEMANTIC_MISMATCH_NOTES` —— 选中的控件与描述几乎无关（重叠度 ~0）
    但它们**只收集、没人读** == 白收集。这类用例注定「换个环境就崩」或
    「实跑报元素语义未找到」，而 L1 还傻乎乎地去试跑它 ——
    跑过了只证明「在这批数据上侥幸能过」，跑挂了又浪费一轮 LLM 重试。

口径：L1 校验**先看这两个清单**，非空就直接带原因返回 False（不试跑），
      让重试闭环让 AI 带着**具体是第几步、哪个值**重生成。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.tools.explore import explorer  # noqa: E402
import framework.cli as cli  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_notes():
    """每条判据前后都清空收集器（它们是**模块级**状态，判据之间会串味）。"""
    for name in ("_HARDCODED_NOTES", "SEMANTIC_MISMATCH_NOTES"):
        getattr(explorer, name).clear()
    yield
    for name in ("_HARDCODED_NOTES", "SEMANTIC_MISMATCH_NOTES"):
        getattr(explorer, name).clear()


def test_hardcoded_notes_make_l1_fail_with_reason(monkeypatch):
    """有「写死行数据」-> L1 判 False，且原因里带**具体是哪一步、写了什么**。"""
    explorer._HARDCODED_NOTES.append("第 4 步(等价直达新建订单页): value='...contract_no=HT-1001'")
    ok, reasons = cli._verify_cases_detailed([("场景A", "用例1")])
    assert ok is False, "写死了行数据却还去试跑 -> 白烧一轮 LLM"
    assert "写死" in reasons and "HT-1001" in reasons, "原因里没有具体是哪一步/哪个值，AI 改不动"


def test_semantic_mismatch_notes_make_l1_fail_with_reason(monkeypatch):
    """有「严重误选控件」-> L1 判 False，且原因里带步骤与重叠度。"""
    explorer.SEMANTIC_MISMATCH_NOTES.append(
        "第 3 步「打开角色切换菜单」选的控件「超@合同列表页」与描述重叠度 0.00(几乎无关)")
    ok, reasons = cli._verify_cases_detailed([("场景A", "用例1")])
    assert ok is False
    assert "重叠度" in reasons or "误选" in reasons


def test_notes_are_cleared_or_absent_means_normal_path(monkeypatch):
    """**反向自证**：清单为空时**不许**走这条短路（否则每次校验都被拦死）。"""
    called = {"gen": False}
    monkeypatch.setattr(cli, "run_capture",
                        lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})())
    ok, reasons = cli._verify_cases_detailed([("场景A", "用例1")])
    # 空清单路径会走到 generate（这里 mock 成失败）-> 说明短路没被误触发
    assert "写死" not in reasons and "误选" not in reasons
