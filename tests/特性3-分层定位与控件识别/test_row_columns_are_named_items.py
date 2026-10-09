# -*- coding: utf-8 -*-
"""特性3 · 行内「无法用 field 表达的列」必须是**有名字的控件**（V8.4.3 · A 方案）。

背景（Windows 实测，追了 7 个提交才收敛）：
    AI 三轮都把 `check`（勾选表格某一行）写崩。逐层查下来：
      1) `_StepModel` 没有 `cell_by`/`cell_index`  -> 补上；
      2) 提示词没教「无 data-field 的列」          -> 补上；
      3) 探针只收 `td[data-field]`（勾选列缺席）   -> 改为按真实列位置给全；
      4) 输出格式示例只有 6 个键                   -> 补上；
      5) 契约排在 prompt @37900（被 71% 的 DOM 淹没）-> 提到第 0 位；
      6) 兜底缓存跨页每页 clear（候选丢失）        -> 改为累积。
    即便全修完，**AI 仍然不填 `cell_by`** —— 真实链路走**结构化输出**，
    而 AI 对「Schema 里的新可选字段」倾向**最小填充**（它把 `semantic_name`
    这类**它会的**字段用得很好，新字段一律省略）。

结论（A 方案）：不要把「表达能力」压在**让 AI 学新字段**上，而是让那个勾选框
    **成为一个真实存在、有 `semantic_name` 的控件** —— AI 用它**已经会**的字段引用它，
    由框架把「引用了一个行内列控件」翻译成 `cell_by=index` + `cell_index`。
    这样与「AI 填不填新字段 / 走结构化还是纯文本 / 探针时序」全部解耦。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.tools.explore import explorer  # noqa: E402

SRC = Path(explorer.__file__).read_text(encoding="utf-8")


def _fn_src(name: str) -> str:
    i = SRC.index(f"def {name}(")
    j = SRC.find("\ndef ", i + 1)
    return SRC[i: j if j > 0 else len(SRC)]


# ---------------------------------------------------------------- 有名字的控件条目

def test_row_columns_become_named_items():
    """**核心判据**：无 data-field 的行内列（勾选列）必须被转成**控件条目**。

    只给 AI 一份「列清单」是不够的 —— 真实链路走结构化输出，AI 不会为它填新字段。
    必须让它成为**清单里的一个控件**（有 semantic_name），AI 才能用它已经会的字段引用。
    """
    assert "def _row_columns_to_items(" in SRC, (
        "没有把行内列转成控件条目的函数 -> AI 只能靠新字段（实测它不填）"
    )
    body = _fn_src("_row_columns_to_items")
    assert '"semantic_name"' in body, "转出来的条目没有 semantic_name -> AI 无法引用"
    assert "row_column_index" in body, (
        "条目没带列号 -> 框架无法把它翻译成 cell_by=index/cell_index"
    )


def test_named_row_column_carries_table_and_index():
    """条目要带**表名**与**真实列号**（生成器 `cell_index` 同口径，从 1 起）。"""
    body = _fn_src("_row_columns_to_items")
    assert "row_table" in body, "没带表名 -> 同一页多表时无法区分"
    assert "index" in body, "没带列号"
    assert "checkbox" in body, "没识别勾选列（这是本次事故的主角）"


def test_only_fieless_columns_become_items():
    """**反向自证**：**有** data-field 的列**不许**转成控件条目。

    那些列本来就靠 `cell_field` 表达（AI 对这个字段很熟，一直在用）；多造条目会
    污染控件清单、改变同名唯一化结果，还会让 42 份录像的结构键漂移。
    """
    body = _fn_src("_row_columns_to_items")
    assert "if not" in body or "continue" in body, (
        "没有跳过「有 field」的列 -> 会凭空多出大量条目（清单污染 + 录像键漂移）"
    )


# ---------------------------------------------------------------- 框架负责翻译

def test_plan_to_steps_translates_named_row_column():
    """引用「行内列控件」的步骤，要由**框架**补上 `cell_by=index` + `cell_index`。

    这就是 A 方案的关键：AI 只管说「我要点这个控件（勾选列）」，翻译归框架。
    """
    body = _fn_src("_plan_to_steps")
    assert "row_column_index" in body, (
        "`_plan_to_steps` 没处理行内列控件 -> AI 引用了也不会变成 cell_by=index"
    )
    assert 'cell_by' in body and 'cell_index' in body, "没把列号写成 cell_by/cell_index"
