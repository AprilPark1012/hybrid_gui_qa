"""V8.7.15 判据：`expect_first_row` 把**表头文案**当 data-field 时，按 header 唯一反查补正。

由来（2026-10-29 用户 V8.7.14 二次实测，同场景同清空起点）：
  第一次：AI 第 2 轮自己改对 -> 391s PASSED
  第二次：AI **两轮都写** `cell_field='订单名称'`（中文表头）-> 716.8s FAILED、再一轮也 FAILED
  报错都是「表格没有第一行、或没有 '订单名称' 列 —— 无法验证「第一条记录」」。

  生成出的选择器：`tbody tr:first-child td[data-field='订单名称']` —— 永远命中 0 个，
  真正的列是 `data-field='orderName'`。

  => 起点相同而 AI 时对时错 = **非确定性**，不能赌它「下次会改对」，框架必须自己兜。

补正**不是猜**：`probe_row_fields()` 给的是 `{"field": "orderName", "header": "订单名称"}`，
header 是页面真实表头、field 是真实 data-field，AI 写了 header -> 反查 field 是**唯一映射**。
但**只在唯一解时改**：同一 header 命中多列（多表都有「订单名称」但 field 不同）就原样不动。
"""
from __future__ import annotations



class _Step:
    def __init__(self, op: str, cell_field: str | None = None, order: int = 1):
        self.op = op
        self.cell_field = cell_field
        self.order = order


ROW_FIELDS = [
    {"table": "orders", "field": "orderName", "header": "订单名称", "index": 2, "kind": ""},
    {"table": "orders", "field": "orderNo", "header": "订单编号", "index": 1, "kind": ""},
    {"table": "orders", "field": "customer", "header": "客户", "index": 3, "kind": ""},
]


def test_header_text_is_translated_to_data_field() -> None:
    """① 核心：中文表头 `订单名称` -> 真正的 `orderName`。"""
    from framework.features.f02_semantic.explorer_explore import _fix_first_row_column_by_header as f

    st = _Step("expect_first_row", "订单名称")
    notes = f([st], ROW_FIELDS)
    assert st.cell_field == "orderName", f"没补正，实际还是 {st.cell_field!r}"
    assert notes and "订单名称" in notes[0] and "orderName" in notes[0], (
        "补正必须出声说明「从什么改成什么」—— 静默改动数据是不允许的"
    )


def test_valid_field_untouched() -> None:
    """② 本来就是合法 data-field -> 一个字节都不动。"""
    from framework.features.f02_semantic.explorer_explore import _fix_first_row_column_by_header as f

    st = _Step("expect_first_row", "orderNo")
    assert f([st], ROW_FIELDS) == []
    assert st.cell_field == "orderNo"


def test_ambiguous_header_not_touched() -> None:
    """③ 同一表头命中多列（不同表同名表头）-> **不改**，交给警告 + AI 重试。

    这条守「唯一解才补」—— 多表都有「订单名称」列时，选哪个都是猜。
    """
    from framework.features.f02_semantic.explorer_explore import _fix_first_row_column_by_header as f

    multi = [
        {"table": "orders", "field": "orderName", "header": "订单名称"},
        {"table": "invoices", "field": "invoiceOrderName", "header": "订单名称"},
    ]
    st = _Step("expect_first_row", "订单名称")
    assert f([st], multi) == []
    assert st.cell_field == "订单名称", "多义时必须原样保留，不能猜一个"


def test_unknown_text_not_touched() -> None:
    """④ 表头里根本找不到 -> 不改（诚实降级，绝不编一个 field）。"""
    from framework.features.f02_semantic.explorer_explore import _fix_first_row_column_by_header as f

    st = _Step("expect_first_row", "根本不存在的列")
    assert f([st], ROW_FIELDS) == []
    assert st.cell_field == "根本不存在的列"


def test_columns_without_data_field_cannot_be_fixed() -> None:
    """⑤ 列没有 data-field（清单里 field 为空）-> 无从反查，不改。

    典型：勾选列 `<td><input type=checkbox></td>`，它在清单里 field 是空串。
    """
    from framework.features.f02_semantic.explorer_explore import _fix_first_row_column_by_header as f

    only_kind = [{"table": "orders", "field": "", "header": "勾选", "kind": "checkbox"}]
    st = _Step("expect_first_row", "勾选")
    assert f([st], only_kind) == []
    assert st.cell_field == "勾选"


def test_other_ops_ignored() -> None:
    """⑥ 只碰 `expect_first_row` —— 别的 op 的 cell_field 语义不同，不许误改。"""
    from framework.features.f02_semantic.explorer_explore import _fix_first_row_column_by_header as f

    fill = _Step("fill", "订单名称")
    click = _Step("click", "订单名称")
    assert f([fill, click], ROW_FIELDS) == []
    assert fill.cell_field == "订单名称" and click.cell_field == "订单名称"


def test_ordering_fix_runs_before_warn() -> None:
    """⑦ 接线顺序：补正**必须在**警告之前 —— 否则「能补的」也会被报成警告。"""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "framework/features/f02_semantic/explorer_explore.py"
    text = src.read_text(encoding="utf-8")
    # V8.7.26：两个调用点都多了 pages=pages（且补正那行跨行了）-> 一律用前缀匹配，
    #   只钉**数据源必须是 _ALL_ROW_FIELDS**（这才是本判据要守的东西），不钉括号位置。
    i_fix = text.find("_fix_first_row_column_by_header(steps, _ALL_ROW_FIELDS or None")
    i_warn = text.find("_warn_nonexistent_row_columns(steps, _ALL_ROW_FIELDS or None")
    assert i_fix > 0 and i_warn > 0, "调用点没找到"
    assert i_fix < i_warn, "补正必须排在警告之前（先修补、再报剩下的）"
