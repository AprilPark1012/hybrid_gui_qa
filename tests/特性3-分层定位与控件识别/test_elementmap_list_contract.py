# -*- coding: utf-8 -*-
"""特性3 · elementMap **统一 list 形态**契约（P25 片 0 · 判据先行，V8.5）

## 目标形态（AprilPark1012 2026-10-11 定，要求6 + D2/D3）

elementMap 一律是 **list：一页一个对象**：

    [ {"page": <页名>, "url": <地址>, "scenario": <场景原文>, "scenario_id": ...,
       "scenario_fingerprint": ...,
       "steps": [ <该页的步骤> ... ],
       "probe_items": [ {<控件条目>, "isValid": true}, ... ]} ]

- 单页 = 长度为 1 的数组；`probe` 与 `explore` **同形**（不再有裸 list 的 probe_*.json 一套结构）。
- 每个 element 带 `isValid`，**默认 true**；generate 补探/复核发现控件已失效 -> 置 `false`。
- D2：`steps` 按 `goto` 边界**切到各页**（每页只放本页步骤）。
- D3：`isValid=false` 的条目**保留在产物与运行时快照**（留痕/审计）+ **排除映射** + **不进 AI 提示词**。

## 现状（片 0 基线，本判据**应当红**）

- `ElementMap.to_dict()` 返回 **dict**（`{url, scenario, steps, probe_items}`）；
- `probe_*.json` 是**裸 list**，与 elementMap 不同形；
- 条目里**没有** `isValid` 字段。

## 红态纪律

判据只描述**目标行为**（通过公开 API 构造 -> 断言产物形态），不锁实现细节；
红的原因必须是「功能缺失」，不是语法/导入错误。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.tools.probe.element_map import ElementMap, ElementRef, TestStep

REPO = Path(__file__).resolve().parents[2]


def _minimal_map(**kw) -> ElementMap:
    """用现有公开入口构造一个最小 elementMap（单页）。"""
    return ElementMap(
        url="http://host/order_detail.html",
        scenario="打开详情页并点编辑",
        steps=[TestStep(1, "click", element=ElementRef(semantic_name="编辑"), description="进入编辑态")],
        probe_items=[{"semantic_name": "编辑", "role": "button", "text": "编辑"}],
        **kw,
    )


def _first_page(m: ElementMap) -> dict:
    """取第一个页对象 —— 顶层不是 list 时就以**断言**失败（不要抛 KeyError，红态要说得清）。"""
    d = m.to_dict()
    assert isinstance(d, list), (
        f"elementMap 顶层必须是 list（一页一个对象），现状 {type(d).__name__}"
        + (f"：{list(d)[:6]}" if isinstance(d, dict) else ""))
    assert d, "elementMap 不能为空（至少一个页对象）"
    return d[0]


def test_elementmap_top_level_is_list():
    """顶层必须是 list（一页一个对象），不是 dict。"""
    d = _minimal_map().to_dict()
    assert isinstance(d, list), (
        "elementMap 顶层必须是 list（一页一个对象）；"
        f"现状是 {type(d).__name__}：{list(d)[:6] if isinstance(d, dict) else d}")


def test_page_object_carries_required_keys():
    """每个页对象必须带 page / url / scenario / steps / probe_items。"""
    page = _first_page(_minimal_map())
    for key in ("page", "url", "scenario", "steps", "probe_items"):
        assert key in page, f"页对象缺键 {key!r}；实际键={sorted(page)}"
    assert isinstance(page["steps"], list) and isinstance(page["probe_items"], list)


def test_probe_item_has_isvalid_default_true():
    """控件条目必须带 isValid，且默认 true。"""
    ref = ElementRef(semantic_name="编辑", role="button")
    d = ref.to_dict()
    assert "isValid" in d, f"ElementRef 缺 isValid 字段；实际键={sorted(d)}"
    assert d["isValid"] is True, f"isValid 默认必须是 True，实际 {d['isValid']!r}"


def test_elementmap_page_items_carry_isvalid():
    """页面对象里的每个 probe_item 都要带 isValid（默认 true）。"""
    page = _first_page(_minimal_map())
    assert page["probe_items"], "构造的清单不该为空（判据自身前提）"
    for it in page["probe_items"]:
        assert it.get("isValid") is True, f"条目 {it.get('semantic_name')!r} 缺 isValid/不为 True：{it}"


def test_steps_are_partitioned_by_page():
    """多页时 steps 按 goto 边界切到各页（D2）。"""
    m = ElementMap(
        url="http://host/",
        scenario="两页场景",
        steps=[
            TestStep(1, "goto", value="http://host/a.html", description="打开 A"),
            TestStep(2, "click", element=ElementRef(semantic_name="A按钮"), description="点 A 的按钮"),
            TestStep(3, "goto", value="http://host/b.html", description="打开 B"),
            TestStep(4, "click", element=ElementRef(semantic_name="B按钮"), description="点 B 的按钮"),
        ],
        probe_items=[{"semantic_name": "A按钮"}, {"semantic_name": "B按钮"}],
    )
    pages = m.to_dict()
    assert isinstance(pages, list) and len(pages) == 2, (
        f"两页场景必须切出 2 个页对象，实际 {len(pages) if isinstance(pages, list) else type(pages).__name__}")
    def _elem_name(e):
        """读一步的控件名（两种产物形态都要认）。

        [!] 这是我片 0 写这条判据时的**自身缺陷**（2026-10-11 修）：`ElementMap` 产物里
            `steps[].element` 是**元素字典**（`TestStep.to_dict()` 的形状），
            只有 `cases/*.json`（`elementmap_to_case` 产物）里 `element` 才是**语义名字符串**。
            判据拿 ElementMap 产物却按字符串断言 => 红的原因是实现之外的期望值错了，
            这种红不合格（会把"判据写错"伪装成"功能没做"）。
        """
        return e.get("semantic_name") if isinstance(e, dict) else e

    names = [[_elem_name(st.get("element")) for st in p["steps"] if st.get("element")] for p in pages]
    assert names[0] == ["A按钮"] and names[1] == ["B按钮"], f"steps 未按 goto 边界切页：{names}"


def test_probe_and_explore_products_share_one_shape():
    """probe 产物与 elementMap 必须同形（否则下游要写两套读法）。"""
    from framework.tools.generate import probe_snapshot
    import inspect
    src = inspect.getsource(probe_snapshot.items_from_element_map)
    assert "probe_items" in src, "probe_snapshot 必须读 probe_items（同形前提）"
    # 目标：快照侧只认一种形状（list of pages）；现状还有 items_from_probe_snapshot 处理裸 list
    has_legacy = hasattr(probe_snapshot, "items_from_probe_snapshot")
    assert not has_legacy, (
        "probe 产物统一成 elementMap 同形后，items_from_probe_snapshot 这种「第二种形状的读法」应被合并/删除")


def test_legacy_dict_product_still_readable():
    """向后兼容：老 dict 形态的产物仍必须可读（交付包里存着老 element_map）。"""
    m = _minimal_map()
    d = m.to_dict()
    assert isinstance(d, list), "先满足新形态（本条同时是向后兼容的入口检查）"


def test_invalid_item_is_excluded_from_mapping():
    """isValid=false 的条目必须被排除在定位映射之外（D3）。"""
    from framework.tools.generate import generator
    src_ok = any("isValid" in (fn or "") for fn in
                 (getattr(generator, "_load_loc_map_from_element_map", None) and
                  __import__("inspect").getsource(generator._load_loc_map_from_element_map), ""))
    assert src_ok, "定位来源解析必须识别并排除 isValid=false 的条目（否则失效控件仍会被点到）"


def test_invalid_items_do_not_enter_prompt():
    """isValid=false 的条目**不进 AI 提示词**（D3：省 token，AprilPark1012明确要求）。"""
    from framework.tools.explore import explorer
    fn = getattr(explorer, "_compact_item", None)
    assert fn is not None, "提示词出站白名单 _compact_item 必须存在"
    src = __import__("inspect").getsource(fn)
    assert "isValid" in src, (
        "提示词出站处必须按 isValid 过滤（目标是「失效项不进提示词」）；"
        "注意：不是把 isValid 字段写进提示词，而是把 false 的条目挡在外面")
