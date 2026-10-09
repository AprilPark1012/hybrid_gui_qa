# -*- coding: utf-8 -*-
"""特性3 · 行内列清单必须**按真实列位置**给全（V8.4.3 · Windows 实测追到探针层）。

事故链（AprilPark1012 Windows 实测 -> 逐层追下来的）：
    AI 三轮都把 `check`（勾选订单行）写崩：轮 1 element 留空；轮 3 打到了
    `<a href="/contract_detail.html?no=HT-1001">HT-1001</a>`（Not a checkbox）。
    我先补了 schema（`cell_by`/`cell_index`）和提示词，**但重跑仍然失败** ——
    AI 改成了自造 `cell_field="pick"`。

追到探针层才看到真正的依据是错的：
    `probe_row_fields` 里
      · `cells = tbl.locator("tbody tr").first.locator("td[data-field]")`  —— **只收有 data-field 的列**，
        而「勾选列」是 `<td><input type=checkbox></td>`（**没有 data-field**）=> 清单里根本没有它。
        提示词又写着「cell_field 只能取下面这些 field，禁止自造」=> AI 无处可写，只能违约束自造。
      · `header = headers[ci]` 里的 `ci` 是**data-field 单元格的序号**，不是**真实列号**
        => 列 = [勾选, 合同编号, 名称] 时，`td[data-field]` 只有 2 个，
           `ci=0` 取到的表头是「勾选」而**不是**「合同编号」（表头错位）。

口径：探针要给「**真实列位置**」的视图 —— 每列都出现，带
  · `index`：真实列号（**从 1 起**，与生成器 `cell_index` 口径一致）
  · `field`：有 data-field 就给，没有就给空串（**不是跳过这一列**）
  · `header`：**按真实列号对齐**的表头
  · `kind`：没有 data-field 的列标注其控件种类（checkbox/radio/…），让 AI 知道「这列是勾选框」
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.tools.probe import probe as probe_mod  # noqa: E402

SRC = Path(probe_mod.__file__).read_text(encoding="utf-8")


def _fn_src(name: str) -> str:
    i = SRC.index(f"def {name}(")
    j = SRC.find("\ndef ", i + 1)
    return SRC[i: j if j > 0 else len(SRC)]


# ---------------------------------------------------------------- 覆盖「无 data-field 的列」

def test_row_fields_include_columns_without_data_field():
    """**核心判据**：没有 data-field 的列（勾选列）也必须出现在清单里。

    只收 `td[data-field]` => 勾选列缺席 => AI 无处可写 => 只能自造一个假 field。
    """
    body = _fn_src("probe_row_fields")
    assert 'locator("td[data-field]")' not in body, (
        "仍然只收 td[data-field] 的列 -> 勾选列（无 data-field）缺席，AI 只能自造 field"
    )
    assert 'locator("td")' in body, "没有按**全部 td** 遍历 -> 无 data-field 的列会被跳过"


def test_row_fields_carry_real_column_index():
    """每列必须带 `index`（**真实列号，从 1 起**）—— 生成器 `cell_index` 就是这个口径。"""
    body = _fn_src("probe_row_fields")
    assert '"index"' in body or "'index'" in body, (
        "清单里没有 index -> AI 无法用 cell_by=index 表达「第 1 列的勾选框」"
    )
    assert "+ 1" in body or "ci + 1" in body or "i + 1" in body, (
        "index 没从 1 起（生成器口径是第 1 列 = 1；从 0 起会取到最后一列，生成器会拦下）"
    )


def test_row_fields_header_is_aligned_to_real_column():
    """**反向自证**：表头必须按**真实列号**对齐 —— 不许再用 data-field 单元格的序号去索引。

    这是实测的第二个缺陷：列 = [勾选, 合同编号] 时，data-field 序号 0 拿到的是表头「勾选」。
    """
    body = _fn_src("probe_row_fields")
    code = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    # 关键：**同一个**真实列号同时用于 td 与 headers（不许一个用 data-field 序号、一个用真实列号）
    assert 'locator("td")' in code, (
        "td 不是按真实列位置遍历 -> 序号与表头对不上（表头错位）"
    )
    assert "headers[ci]" in code.replace(" ", ""), (
        "表头没用同一个真实列号索引 -> 表头会错位"
    )


def test_row_fields_mark_checkbox_kind():
    """无 data-field 的列要标出控件种类，AI 才知道「这列是勾选框」。"""
    body = _fn_src("probe_row_fields")
    assert "kind" in body, "没有 kind 字段 -> AI 看不出「第 1 列是勾选框」"
    assert "checkbox" in body, "没有识别 checkbox 列"


# ---------------------------------------------------------------- 提示词要交底

def test_prompt_tells_ai_about_column_index():
    """提示词必须把列的 `index` 交给 AI（光有 cell_by 字段名不够）。"""
    from framework.tools.explore import explorer

    src = Path(explorer.__file__).read_text(encoding="utf-8")
    # [!] 必须在 `_build_planner_prompt` **函数体内**找：文件名里 "表格行内列清单" 另有一处
    #     （注释/其它函数），全局 index 会撞到它 -> 判据误红（踩过一次）。
    fi = src.index("def _build_planner_prompt(")
    fj = src.find("\ndef ", fi + 1)
    body = src[fi: fj if fj > 0 else len(src)]
    i = body.index("表格行内列清单")
    seg = body[i: i + 1600]
    assert "index" in seg, (
        "行内列清单那段没提 index -> AI 仍不知道勾选列是第几列（实测它只能自造 field）"
    )
