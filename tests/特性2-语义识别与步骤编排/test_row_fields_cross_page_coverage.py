"""V8.7.18 判据：列清单预检/反查必须覆盖**所有探测过的页**（跨页不许误报）。

由来（2026-10-29 用户真链路日志，第 2 轮）：
  第 63 步在**发票列表页**要查「合同编号」（用户确认该页**确实有这一列**），
  框架却报：
      [!] 有 1 步 expect_first_row 要查的列不在本次探测到的列里
          探测到的列: businessUnit、contractName、contractNo、customer、...
          - 第 63 步 要查列 '合同编号'
  而这份列清单是**订单列表页**的 —— `_LAST_ROW_FIELDS` 只保留**最后一次**探测的页。

  => 假阳性。AI 写对了，框架冤枉它。V8.7.15 当初的注释就预见到「跨页时可能误报」，
     现在用 `_ALL_ROW_FIELDS`（累积所有探测过的页）把它从「预见到」变成「修掉」。

守三件事：
  ① 预检/反查**必须**读 `_ALL_ROW_FIELDS`，不许再读 `_LAST_ROW_FIELDS`；
  ② `_ALL_ROW_FIELDS` 在「每次探测」时**只累积不清**（清了就退化成最后一页）；
  ③ `_ALL_ROW_FIELDS` 必须按**轮次**清空（多轮重试不能串味）；
  ④ `_LAST_ROW_FIELDS` 保持原语义（`_fill_missing_row_column` 依赖「最后一页」判勾选列唯一解）。
"""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "framework/features/f02_semantic/explorer_explore.py"


def _src() -> str:
    return SRC.read_text(encoding="utf-8")


def test_precheck_reads_all_row_fields() -> None:
    """① 预检与反查都读 `_ALL_ROW_FIELDS`。"""
    s = _src()
    assert "_warn_nonexistent_row_columns(steps, _ALL_ROW_FIELDS or None, pages=pages)" in s, (
        "列名预检还在读 _LAST_ROW_FIELDS —— 跨页会误报「列不存在」"
    )
    # V8.7.26：调用点改成跨行了（多了 pages=pages）-> 用前缀匹配，只钉数据源是 _ALL_ROW_FIELDS
    assert "_fix_first_row_column_by_header(steps, _ALL_ROW_FIELDS or None" in s, (
        "表头反查还在读 _LAST_ROW_FIELDS —— 跨页时反查不到，白白放过能修的错"
    )
    # 反向：不许再出现把 _LAST 传给这两个函数
    assert "_warn_nonexistent_row_columns(steps, _LAST_ROW_FIELDS" not in s
    assert "_fix_first_row_column_by_header(steps, _LAST_ROW_FIELDS" not in s


def test_all_row_fields_accumulates_not_cleared_per_probe() -> None:
    """② 每次探测只累积、不清 —— 清了就退化成「只有最后一页」。"""
    s = _src()
    # 定位「每次探测」那段：_LAST clear+extend 与 _ALL extend 必须在一起
    i = s.find("_LAST_ROW_FIELDS.clear(); _LAST_ROW_FIELDS.extend(row_fields)")
    assert i > 0, "找不到每次探测的赋值处"
    seg = s[i : i + 700]
    assert "_ALL_ROW_FIELDS.extend(row_fields)" in seg, (
        "每次探测没有累积到 _ALL_ROW_FIELDS —— 跨页清单不全，误报照旧"
    )
    assert "_ALL_ROW_FIELDS.clear()" not in seg, (
        "每次探测都清 _ALL_ROW_FIELDS —— 又只剩最后一页了（这正是要修的 bug）"
    )


def test_all_row_fields_cleared_per_round() -> None:
    """③ 按轮次清空（多轮重试不能串味）。"""
    s = _src()
    i = s.find("_LAST_REQUIRED_FIELDS.clear()")
    assert i > 0, "找不到轮次清空段"
    seg = s[max(0, i - 80) : i + 400]
    assert "_ALL_ROW_FIELDS.clear()" in seg, (
        "轮次开始没清 _ALL_ROW_FIELDS —— 上一轮的列会留到本轮，跨轮串味"
    )


def test_last_row_fields_semantics_unchanged() -> None:
    """④ `_LAST_ROW_FIELDS` 保持「最后一页」语义（_fill_missing_row_column 依赖它）。"""
    s = _src()
    i = s.find("def _fill_missing_row_column")
    assert i > 0
    seg = s[i : i + 4000]
    assert "_LAST_ROW_FIELDS" in seg, (
        "勾选列唯一解判定不再用 _LAST_ROW_FIELDS —— 改成跨页并集可能让「唯一解」失效"
        "（不同页的勾选列号可能不同，并集就不再唯一）"
    )


def test_behavior_single_page_still_detects_bad_column(capsys) -> None:
    """行为层：单页场景下，真不存在的列仍要被报出来（放宽不能放成瞎眼）。"""
    class _S:
        op = "expect_first_row"
        cell_field = "根本不存在的列"
        order = 63
        page = ""

    from framework.features.f02_semantic.explorer_explore import _warn_nonexistent_row_columns

    fields = [{"table": "t", "field": "contractNo", "header": "合同编号"}]
    notes = _warn_nonexistent_row_columns([_S()], fields)
    out = capsys.readouterr().out
    assert notes and "根本不存在的列" in out


def test_behavior_cross_page_column_no_longer_false_alarm(capsys) -> None:
    """行为层：跨页清单里能反查到的列 -> 补正后**不再**被报成「列不存在」。

    [!] 注意顺序：`合同编号` 本身确实不是合法 data-field，所以**补正前**告警是对的
        （那是在提醒「你写的不是 field」）。生产接线是**先补正、再警告**，
        补正之后它变成 contractNo，警告自然不该再出现 —— 这条判据验的就是这个闭环。
        （我第一版把「补正前也该无警告」写成断言，是错的，被自己抓出来。）
    """
    class _S:
        def __init__(self):
            self.op = "expect_first_row"
            self.cell_field = "合同编号"
            self.order = 63
            self.page = "发票列表页"

    from framework.features.f02_semantic.explorer_explore import (
        _fix_first_row_column_by_header,
        _warn_nonexistent_row_columns,
    )

    # 累积清单：订单列表页 + 发票列表页的列都在里面
    all_fields = [
        {"table": "orders", "field": "orderNo", "header": "订单编号"},
        {"table": "invoices", "field": "contractNo", "header": "合同编号"},
    ]
    st = _S()
    fixed = _fix_first_row_column_by_header([st], all_fields)
    assert st.cell_field == "contractNo", "跨页清单里能反查到，却没补正"
    assert fixed, "补正没出声"
    capsys.readouterr()

    # 补正之后，再走警告 —— 此时它已是合法 field，不许再报
    notes = _warn_nonexistent_row_columns([st], all_fields)
    assert notes == [], f"补正后仍报警（假阳性未修）：{notes}"
    assert capsys.readouterr().out == ""
