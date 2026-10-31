# -*- coding: utf-8 -*-
"""非 `<table>` 的行内列（div 网格）必须被探测到（V8.7.29）。

真实现场（2026-10-31 实测取证）
------------------------------
`demo/order_detail.html` 的明细行**不是 `<table>`**，是 div 网格：

    <div class="lines-grid" id="lines-grid">
      <div class="head">操作</div><div class="head">行号</div>...     <- 表头 10 个
      <div class="cell">...</div>
      <div class="cell" data-field="lineNo">{{ idx + 1 }}</div>
      ...
      <div class="cell" data-field="lineStatus">{{ ln.status }}</div>
    </div>

`probe_row_fields` 第一行就是 `page.locator("table")` —— 这类页面**一条列都探不到**
（真机实测 0 条）。于是 AI 永远不知道 `lineNo` / `lineStatus` 可用；它要做行内断言
只能瞎猜列名，猜出来的运行时必然找不到。

判据口径
--------
1. `probe_div_grid_fields` 能从 `evaluate` 的结果正确组装出与 `probe_row_fields`
   **同构**的条目（`{table,index,field,header,kind}`）；
2. 同一个网格里**同名列只留一条**（div 每行都重复渲染 data-field，不去重会随行数膨胀）；
3. `field` 为空的条目跳过（没有 data-field 不算"列字段"）；
4. `evaluate` 抛异常时返回空列表，**不许炸**（探测失败不能把整条链路带下去）；
5. **接线**：`probe_row_fields` 默认真的调用了它（`include_div_grids=True`），
   且 `<table>` 路径**一行没动**（老行为可关掉新路径复现）。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "framework" / "features" / "f03_locate" / "probe.py"


def _src() -> str:
    assert PROBE.is_file(), f"找不到 {PROBE}"
    return PROBE.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_src())


def _func(name: str) -> ast.FunctionDef:
    for n in ast.walk(_tree()):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError(f"模块里找不到函数 {name}")


class _FakePage:
    """只实现 `evaluate` —— `probe_div_grid_fields` 只用这一个能力。"""

    def __init__(self, rows, boom: bool = False):
        self._rows = rows
        self._boom = boom
        self.calls = 0

    def evaluate(self, js):                     # noqa: ARG002 —— 只关心返回
        self.calls += 1
        if self._boom:
            raise RuntimeError("evaluate 故意炸")
        return self._rows


def _grid_row(field: str, idx: int, header: str = "", per_row: int = 10, grid: str = "lines-grid"):
    return {"grid": grid, "field": field, "index": idx, "perRow": per_row, "header": header}


# ---------------------------------------------------------------- 1) 组装
def test_div_grid_fields_are_shaped_like_table_row_fields():
    from framework.features.f03_locate.probe import probe_div_grid_fields

    page = _FakePage([_grid_row("lineNo", 13, "行号"), _grid_row("lineStatus", 20, "状态")])
    got = probe_div_grid_fields(page)
    assert len(got) == 2, got
    keys = set(got[0])
    assert keys == {"table", "index", "field", "header", "kind"}, (
        f"条目必须与 probe_row_fields 同构，实际键: {sorted(keys)}")
    assert got[0]["field"] == "lineNo" and got[0]["header"] == "行号"
    assert got[1]["field"] == "lineStatus" and got[1]["header"] == "状态"
    assert all(x["table"] == "lines-grid" for x in got)


def test_div_grid_dedups_same_field_across_rows():
    """同一网格里同名列只留一条（2 行数据会让 lineNo 重复出现）。"""
    from framework.features.f03_locate.probe import probe_div_grid_fields

    page = _FakePage([
        _grid_row("lineNo", 13, "行号"), _grid_row("lineStatus", 20, "状态"),
        _grid_row("lineNo", 23, "行号"), _grid_row("lineStatus", 30, "状态"),
    ])
    got = probe_div_grid_fields(page)
    fields = [x["field"] for x in got]
    assert fields == ["lineNo", "lineStatus"], f"同名列必须去重，实际: {fields}"


def test_div_grid_skips_empty_field():
    from framework.features.f03_locate.probe import probe_div_grid_fields

    page = _FakePage([_grid_row("", 1, "选择"), _grid_row("lineNo", 13, "行号")])
    got = probe_div_grid_fields(page)
    assert [x["field"] for x in got] == ["lineNo"], "没有 data-field 的单元格不算列字段，必须跳过"


def test_div_grid_survives_evaluate_error():
    from framework.features.f03_locate.probe import probe_div_grid_fields

    page = _FakePage([], boom=True)
    assert probe_div_grid_fields(page) == [], "evaluate 抛异常时必须返回空列表，不许把链路带崩"


def test_div_grid_empty_page_returns_empty():
    from framework.features.f03_locate.probe import probe_div_grid_fields

    assert probe_div_grid_fields(_FakePage([])) == []


def test_div_grid_header_stays_empty_when_uninferable():
    """推断不出表头时留空串（空表头比错表头安全）。"""
    from framework.features.f03_locate.probe import probe_div_grid_fields

    got = probe_div_grid_fields(_FakePage([_grid_row("lineNo", 13, "")]))
    assert got and got[0]["header"] == ""


# ---------------------------------------------------------------- 2) 接线（静态，AST）
def test_js_skips_cells_inside_table():
    """JS 里必须 `closest('table')` 跳过表格内元素，否则与 table 路径重复产出。"""
    src = _src()
    assert "closest('table')" in src, (
        "div 网格探测必须跳过 `<table>` 内的 [data-field] —— "
        "否则同一列会被 table 路径和 div 路径各产出一条，清单里出现重复项")


def test_row_fields_call_extends_div_grids():
    fn = _func("probe_row_fields")
    body = ast.get_source_segment(_src(), fn) or ""
    assert "probe_div_grid_fields(page)" in body, (
        "`probe_row_fields` 必须真的调用 `probe_div_grid_fields(page)` —— "
        "光定义了新函数不接线，等于没修（接线判据是标配）")


def test_row_fields_defaults_include_div_grids_true():
    fn = _func("probe_row_fields")
    defaults = {}
    args = fn.args.args
    kdefaults = fn.args.defaults
    for a, d in zip(args[len(args) - len(kdefaults):], kdefaults):
        defaults[a.arg] = d
    assert "include_div_grids" in defaults, "`probe_row_fields` 必须有 `include_div_grids` 开关"
    node = defaults["include_div_grids"]
    assert isinstance(node, ast.Constant) and node.value is True, (
        "`include_div_grids` 必须**默认 True** —— 生产路径永远要探 div 网格；"
        "默认关掉等于新能力只在判据里存在")


def test_table_path_unchanged_when_div_grids_off():
    """关掉新路径时，table 那段必须还在（老行为可复现）。"""
    fn = _func("probe_row_fields")
    body = ast.get_source_segment(_src(), fn) or ""
    assert 'page.locator("table")' in body, "<table> 路径被删掉了？老行为必须保留"
    assert "if include_div_grids:" in body, "新路径必须挂在开关下，便于单独验证老行为"
