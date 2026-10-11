# -*- coding: utf-8 -*-
"""特性3 · 行定位字段必须**落到 cases/*.json**（P25 片 2 · 判据先行后补，V8.5）

## 为什么单独立这条判据（教训）

`apply_row_locator_fallback()`（explorer.py:1555 / generator.py:689）会补 `row_index` ——
但 `elementmap_to_case` 当时**不读它**，于是「explore 补了、写 cases 时丢了」，
而`test_row_locate_uses_scope.py` 只测**渲染层** -> 这条链**没有判据守着**、一直没红。

实测症状（V8.4.6 端到端）：AI 用例 0 步带 `row_index`，生成脚本里却有 `_act_row(..., -1, ...)`
（渲染期兜底又补了一次），运行期仍报 `元素定位失败且自愈未成功: 物料编码@订单详情页`。

=> 口径：**给 AI 的产出 schema 加字段 = 构造点 → TestStep → to_dict → elementmap_to_case 透传
→ 闸门判定 → 清单防截断，六处都要查**（本项目 V8.4.3 为同类问题追过 13 个提交）。
本判据守的是「透传」这一处。
"""
from __future__ import annotations

import inspect
from pathlib import Path

from framework.tools.generate.case_builder import elementmap_to_case
from framework.tools.probe.element_map import ElementMap, ElementRef, TestStep

REPO = Path(__file__).resolve().parents[2]


def _map_with_row_index(ri):
    return ElementMap(
        url="http://host/order_detail.html",
        scenario="填行内字段",
        steps=[TestStep(1, "fill", element=ElementRef(semantic_name="物料编码@订单详情页"),
                        value="M001", row_index=ri, description="填第一行物料编码")],
        probe_items=[{"semantic_name": "物料编码@订单详情页"}],
    )


def test_row_index_lands_in_case():
    """elementMap 的 row_index 必须原样落到 cases（否则兜底白补）。"""
    case = elementmap_to_case(_map_with_row_index(-1), case_id="p25_ri")
    step = case["steps"][0]
    assert step.get("row_index") == -1, (
        f"row_index 没落进 cases（实际 keys={sorted(step)}）—— "
        "explore/渲染期的兜底补出来的值会在这一步丢掉")


def test_row_index_is_int_not_bool():
    """落盘的 row_index 必须是 int（bool 是 int 的子类，别让 True 混进来当第 1 行）。"""
    case = elementmap_to_case(_map_with_row_index(2), case_id="p25_ri2")
    v = case["steps"][0].get("row_index")
    assert isinstance(v, int) and not isinstance(v, bool) and v == 2, f"实际 {v!r}"


def test_absent_row_index_leaves_no_key():
    """没给 row_index 时不许写 None 进去（避免下游 `is not None` 判定被 None 骗过）。"""
    case = elementmap_to_case(_map_with_row_index(None), case_id="p25_ri3")
    assert "row_index" not in case["steps"][0], f"不该有该键：{case['steps'][0]}"


def test_text_fallback_path_keeps_row_fields():
    """文本兜底路径（_parse_steps_text）同样要带全行定位字段（防 schema 漂移）。"""
    from framework.tools.explore import explorer
    src = inspect.getsource(explorer._parse_steps_text)
    for key in ("row_text", "cell_field", "cell_by", "cell_index", "row_index"):
        assert key in src, (
            f"文本兜底路径没透传 {key} —— 结构化输出能表达的，文本路径表达不了 = schema 漂移")


def test_generator_reads_row_index_from_case_step():
    """生成期必须认 cases 里的 row_index（两个链路共同收口）。"""
    from framework.tools.generate import generator
    src = inspect.getsource(generator._is_row_index_step)
    assert "row_index" in src, "渲染器没有认 cases 里的 row_index"
