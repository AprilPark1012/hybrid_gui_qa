"""框架能力（P22 批 5 / 方案①）：**不锚容器**的全页 nth —— 处理「同名按钮分布在不同区域」。

真值背景（2026-09-30）：订单详情页有 **2 个** 叫「保存」的按钮：
  · `#btn-save-lines`  在 `section[aria-label="详细信息"]` 里（行保存）
  · `#btn-detail-edit` 在顶部（编辑态下文案变「保存」= 表单保存；非编辑态叫「编辑」）
用例要表达「全页第 2 个『保存』」，但现有渲染把「保存」锚到「详细信息」区 ⇒ 那里只有 1 个
⇒ `nth(1)` 永远落空。新增显式步骤字段 `scope="page"`：**该步不锚任何容器**，
直接在全页范围按元素自身 role/name 取第 N 个。

判据（一类）：
  J1 `scope="page"` ⇒ primary 为 `p.get_by_role(...).nth(N-1)`，**不含** `locator('section`
  J2 不给 scope（向后兼容）⇒ 仍走容器锚分支
  J3 `scope` 值非法 ⇒ 当场失败（禁止静默退回容器锚 —— 那会变成"点了别的按钮"，属假通过）
  J4 `scope="page"` 时 occurrence 仍生效（1 基 → nth(N-1)）
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.tools.generate.generator import (                              # noqa: E402
    _render_pytest_case,
    _semantic_to_locator_expr,
)

ELEM = {
    "semantic_name": "保存@订单详情页",
    "role": "button",
    "name": "保存",
    "text": "保存",
    "tag": "button",
    "anchor": {"kind": "region", "by": "aria_label", "value": "详细信息"},
    "path": [{"axis": "target", "by": "text", "value": "保存"}],
}


def _render(steps):
    """用**真实用例文件**当骨架 ⇒ 渲染走的是与生产同一条路径（含 pages/case_id）。"""
    src = sorted(glob.glob("cases/orders_invoice_full_lifecycle/*.json"))[-1]
    case = json.load(open(src, encoding="utf-8"))
    case["steps"] = steps
    case["asserts"] = []
    # loc_map：semantic_name → locator **表达式字符串**（后缀形态，与生产一致）
    expr = _semantic_to_locator_expr(ELEM)
    return _render_pytest_case(case, {"保存@订单详情页": expr})


def _step(**kw):
    return {"op": "click", "element": "保存@订单详情页", "desc": "点保存", **kw}


def test_j1_page_scope_generates_full_page_nth():
    out = _render([_step(scope="page", occurrence=2)])
    assert "pytest.fail" not in out, f"不该失败：{out[-400:]}"
    # 全页表达可以是 get_by_role / get_by_text（按钮文案用 text 也合理），
    # 关键是：**不带容器锚** + 带序号
    assert ("get_by_role(" in out or "get_by_text(" in out), out
    assert ".nth(1)" in out, out
    assert "locator('section" not in out and 'locator("section' not in out, out


def test_j2_no_scope_keeps_anchor_behavior():
    out = _render([_step()])
    assert "locator('section" in out or 'locator("section' in out, out


def test_j3_invalid_scope_fails_loudly():
    out = _render([_step(scope="container")])
    assert "pytest.fail" in out, out


def test_j4_page_scope_respects_occurrence():
    out = _render([_step(scope="page", occurrence=1)])
    assert "pytest.fail" not in out, f"不该失败：{out[-400:]}"
    assert ".nth(0)" in out, out
