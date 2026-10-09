# -*- coding: utf-8 -*-
"""特性5 · 行内列指定必须**全程透传**（V8.4.3 · 整条链路最后断的一环）。

事故（Windows 实测，追了 13 个提交才真正闭合）：
    AI 三轮都把 `check`（勾选表格某一行）写崩。逐层修下来：
      schema 没字段 -> 补；提示词没教 -> 补；探针漏列 -> 补；格式示例缺键 -> 补；
      契约被 71% 的 DOM 淹没 -> 提到最前 + 挂 system；兜底不触发 -> 修缓存与无效 cell_field；
      行内控件不被看见 -> 插到清单最前。
    中间用「最小复现」拿过铁证：短 prompt 下 AI **能**正确写出 `cell_by=index, cell_index=1`；
    长 prompt 下它写 null（lost in the middle）。所以又加了**框架确定性兜底**（候选唯一才补）。

    **真正最后一环在 `case_builder.py`**：AI 已经写出了 `cell_by`（调试输出可见），
    但从 ElementMap 转成用例 json 时：
      · `item` 只透传 row_text / cell_field，**`cell_by`/`cell_index` 被静默丢掉**；
      · 「行内定位步骤不需要 element」的判定只认 `row_text + cell_field`,
        用 `cell_by=index` 的步骤被判「element 为空」-> L1 当结构性缺陷反复重生成。
    现象就是：产物里只剩 row_text、质量闸一直喊「没有绑定元素」。

教训：**新增一个字段，要连带检查所有「透传/校验/判定」点**，否则前面全做对了也会在这一步消失。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.tools.generate import case_builder  # noqa: E402
from framework.tools.probe.element_map import ElementMap, TestStep  # noqa: E402

SRC = Path(case_builder.__file__).read_text(encoding="utf-8")


def _step(**kw) -> TestStep:
    st = TestStep(order=31, action="check", description="勾选该订单行",
                  row_text="全链路-{datetime}")
    for k, v in kw.items():
        setattr(st, k, v)
    return st


# ---------------------------------------------------------------- 透传

def test_cell_by_is_carried_into_case_json():
    """**核心判据**：`cell_by`/`cell_index` 必须写进用例 json。

    丢在这里的表现：调试输出显示 AI 写了 cell_by，落盘却只剩 row_text，
    下游定位不到、还被判「没绑元素」。
    """
    m = ElementMap(url="http://localhost:8000/x", scenario="s",
                   steps=[_step(cell_by="index", cell_index=1)])
    case = case_builder.elementmap_to_case(m, case_id="c1")
    st = case["steps"][0]
    assert st.get("cell_by") == "index", (
        "cell_by 没透传 -> AI 写了也会在 ElementMap→用例 json 这一步凭空消失"
    )
    assert st.get("cell_index") == 1, "cell_index 没透传 -> 生成器无法定位到列"


def test_cell_field_still_carried():
    """**反向自证**：`cell_field` 路径不许退化（它一直在用）。"""
    m = ElementMap(url="http://x", scenario="s",
                   steps=[_step(cell_field="orderName")])
    st = case_builder.elementmap_to_case(m, case_id="c1")["steps"][0]
    assert st.get("cell_field") == "orderName"
    assert "cell_by" not in st, "没给 cell_by 的步骤不该凭空多出这个键"


# ---------------------------------------------------------------- 判定

def _warn_texts(steps: list[dict]) -> str:
    case = {"case_id": "c1", "name": "n", "base_url": "http://localhost:8000", "steps": steps}
    return " ".join(case_builder.case_warnings(case))


def test_cell_by_index_counts_as_row_locator():
    """判定「行内定位步骤」时必须认 `cell_by=index` —— 否则勾选步骤被判没绑元素。"""
    w = _warn_texts([{"op": "check", "desc": "勾选该订单行",
                      "row_text": "全链路-x", "cell_by": "index", "cell_index": 1}])
    assert "没有绑定元素" not in w, (
        "用 cell_by=index 的行内定位步骤被判「没有绑定元素」-> L1 当结构性缺陷反复重生成"
    )


def test_cell_field_still_counts():
    """反向自证：`cell_field` 那一路的判定不许退化。"""
    w = _warn_texts([{"op": "click", "desc": "点该行订单名称",
                      "row_text": "全链路-x", "cell_field": "orderName"}])
    assert "没有绑定元素" not in w


def test_step_without_any_column_still_flagged():
    """**反向自证**：既无 element 也无列指定的步骤**仍要**报出来（护栏不许被削弱）。"""
    w = _warn_texts([{"op": "check", "desc": "勾选该订单行", "row_text": "全链路-x"}])
    assert "没有绑定元素" in w, (
        "只给了 row_text、没给列 -> 确实无法定位，必须报（不能为了让判据变绿而放过）"
    )
