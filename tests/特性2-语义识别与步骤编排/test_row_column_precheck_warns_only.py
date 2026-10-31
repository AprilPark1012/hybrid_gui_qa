"""V8.7.15 判据：`expect_first_row` 的列名预检必须**只警告、绝不拦**。

由来（2026-10-29 用户 V8.7.14 实测）：
  AI 写了 `expect_first_row` 断言「列表第一条的『订单名称』列」，而订单列表页**没有这一列**。
  实跑 **715 秒**（含 160s 有界等待）后报「表格没有第一行、或没有 '订单名称' 列」→ 用例 FAILED，
  第 2 轮 AI 自己改对才 PASSED（391s）。**那 715 秒纯浪费**。
  而生成阶段其实**已经握着探测到的列清单**（`probe_row_fields`），却没做任何校验。

守两件事：
  ① 提醒**必须真的发生**（列不在清单里时要有输出），否则等于没做；
  ② 提醒**绝不参与拦截** —— 用户 2026-10-29 选 A 时明确「只警告不拦」，
     因为 `_LAST_ROW_FIELDS` 只保留最后一次探测的页，跨页场景必然误报；
     本项目口径是「宁漏不误伤」（误拦会让人绕过闸门，比漏报更糟）。
"""
from __future__ import annotations

import inspect
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
SRC = BASE / "framework/features/f02_semantic/explorer_explore.py"


class _Step:
    """TestStep 的最小替身（只带预检用到的字段）。"""
    def __init__(self, op: str, cell_field: str | None = None, order: int = 1, page: str = ""):
        self.op = op
        self.cell_field = cell_field
        self.order = order
        self.page = page


ROWFIELDS = [
    {"table": "orders", "field": "orderNo", "header": "订单编号", "index": 1, "kind": ""},
    {"table": "orders", "field": "customer", "header": "客户", "index": 2, "kind": ""},
]


def test_warns_when_column_missing(capsys) -> None:
    """① 列不在清单里 -> 必须打印提醒，且说清「要查哪个列」「实际有哪些列」。"""
    from framework.features.f02_semantic.explorer_explore import _warn_nonexistent_row_columns as f

    notes = f([_Step("expect_first_row", "订单名称", order=21)], ROWFIELDS)
    out = capsys.readouterr().out
    # V8.7.24 措辞改成了「按页」口径（跨页串用才是主因），这里接受两套说法，
    #   但**要求必须出现「不在」+ 命名具体列名**（语义保住，不钉字面）。
    assert "不在" in out, "列不存在时必须提醒"
    assert ("列里" in out or "列清单里" in out), "提醒没说清「不在列里」这件事"
    assert "订单名称" in out, "没说要查哪个列，用户看不懂"
    assert "orderNo" in out or "customer" in out, "没列出实际探测到的列，用户没法对照"
    assert notes, "应当把提醒内容返回给调用方"


def test_silent_when_column_exists(capsys) -> None:
    """② 列存在 -> 不许有任何输出（否则每条正常用例都被刷屏）。"""
    from framework.features.f02_semantic.explorer_explore import _warn_nonexistent_row_columns as f

    notes = f([_Step("expect_first_row", "orderNo")], ROWFIELDS)
    assert capsys.readouterr().out == ""
    assert notes == []


def test_silent_without_row_fields(capsys) -> None:
    """③ 没探到列清单 -> 静默（没有依据时不下判断）。"""
    from framework.features.f02_semantic.explorer_explore import _warn_nonexistent_row_columns as f

    assert f([_Step("expect_first_row", "订单名称")], None) == []
    assert f([_Step("expect_first_row", "订单名称")], []) == []
    # 清单里全是空 field（列没 data-field）时也不许乱报
    assert f([_Step("expect_first_row", "订单名称")], [{"field": ""}]) == []
    assert capsys.readouterr().out == ""


def test_other_ops_ignored(capsys) -> None:
    """④ 只查 expect_first_row —— 别的 op 的 cell_field 语义不同，不许误伤。"""
    from framework.features.f02_semantic.explorer_explore import _warn_nonexistent_row_columns as f

    assert f([_Step("fill", "订单名称"), _Step("click", "订单名称")], ROWFIELDS) == []
    assert capsys.readouterr().out == ""


def test_warning_never_blocks(capsys) -> None:
    """⑤ **绝不拦**：`_finalize_map` 里调用它的返回值不得参与任何拦截。

    这是本判据最重要的一条 —— 用户选 A 时的原话是「只警告不拦」，
    因为 `_LAST_ROW_FIELDS` 只保留最后一次探测的页，跨页必然误报。
    """
    from framework.features.f02_semantic.explorer_explore import _warn_nonexistent_row_columns as f

    src = SRC.read_text(encoding="utf-8")
    # 调用点必须**丢弃返回值**（原样语句，不赋值、不判断）
    # V8.7.24：调用现在多传 pages=pages；且该行末尾允许带行尾注释，
    #   所以用正则匹配「整行只有这个裸调用（+ 可选注释）」而不是子串 ——
    #   这样「赋值给变量再 if 判断」仍然会被抓（那是从「警告」变「拦截」）。
    import re as _re
    pat = _re.compile(
        r"^    _warn_nonexistent_row_columns\(steps, _ALL_ROW_FIELDS or None, pages=pages\)"
        r"(\s*#.*)?$", _re.M)
    assert pat.search(src), (
        "调用点不是「丢弃返回值」的裸调用 —— 一旦被赋值拿去 if 判断，就从「警告」变成「拦截」了"
    )
    # 提醒文案必须自陈局限，让人知道跨页时可能误报
    assert "仅供参考、不拦" in inspect.getsource(f), (
        "提醒文案没有标注「仅供参考、不拦」—— 跨页误报时用户会以为是真故障"
    )
    # 行为层再确认一次：即使命中，也不抛异常、不返回阻断信号
    notes = f([_Step("expect_first_row", "订单名称")], ROWFIELDS)
    assert isinstance(notes, list), "返回值必须是纯说明列表，不能是异常/布尔闸门"
    capsys.readouterr()
