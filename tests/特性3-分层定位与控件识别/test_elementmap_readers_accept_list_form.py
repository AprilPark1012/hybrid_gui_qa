# -*- coding: utf-8 -*-
"""特性3 · elementMap 的**所有读取器**都必须能吃 list 形态（P25 片 3 补，防复发）

## 为什么单独立这条（实测事故）

elementMap 的落盘形态从 `dict` 改成 **list（一页一个对象）** 时，读取点一共三处，
我改了 `_load_loc_map_from_element_map`，**漏了另外两处** —— 于是：

    python -m framework.cli all --ai --verify
    -> generate 阶段崩：AttributeError: 'list' object has no attribute 'get'
       （generator.py `_items_from_source`）

`_multi_match_from_source` 同病但更阴：它**不抛**（异常被自己的 `try` 吃掉）-> 返回空 dict
-> **重复控件闸门整体失效**（该拦的不拦，静默放行）—— 这类"静默失效"正是本项目反复追的那类。

=> 口径：形态改了，**每个读取器都要逐条验证**（本项目同类教训：给产出 schema 加字段 = 一处加、六处查）。
本判据锁的是**行为**（拿 list 形态的数据调进去不许炸、且取得到条目），不是源码文本。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

NAME = "物料编码@订单详情页"

#: 新形态：list，一页一个对象
DATA_LIST = [{
    "page": "订单详情页", "url": "http://host/order_detail.html", "scenario": "填新增行",
    "steps": [{"order": 1, "action": "fill", "row_index": -1,
               "element": {"semantic_name": NAME, "role": "textbox", "name": NAME}}],
    "probe_items": [{"semantic_name": NAME, "role": "textbox", "multi_match": 3,
                     "isValid": True}],
}]

#: 老形态：dict（交付包里存着老产物，必须继续可用）
DATA_DICT = {"url": "http://host/order_detail.html", "scenario": "填新增行",
             "steps": DATA_LIST[0]["steps"], "probe_items": DATA_LIST[0]["probe_items"]}


def _write(tmp_path: Path, data) -> Path:
    p = tmp_path / "element_map_x.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.mark.parametrize("data", [DATA_LIST, DATA_DICT], ids=["list_form", "dict_form"])
def test_items_from_source_reads_both_forms(tmp_path, data):
    """`_items_from_source`（锚的唯一来源）：两种形态都要读得到、且不许炸。"""
    from framework.features.f02_semantic.generator_generate import _items_from_source
    got = _items_from_source(_write(tmp_path, data), "element")
    assert NAME in got, f"读不到控件（实际 {sorted(got)[:5]}）—— 形态变了就要在**每个读取器**都改到"


@pytest.mark.parametrize("data", [DATA_LIST, DATA_DICT], ids=["list_form", "dict_form"])
def test_multi_match_from_source_reads_both_forms(tmp_path, data):
    """`_multi_match_from_source`（重复控件信号）：两种形态都要取到 multi_match。

    [!] 这条尤其重要：它坏了**不报错**，只是信号变空 -> 闸门静默失效。
    """
    from framework.features.f02_semantic.generator_generate import _multi_match_from_source
    got = _multi_match_from_source(_write(tmp_path, data), "element")
    assert got.get(NAME) == 3, (
        f"重复控件信号取不到（实际 {got}）—— 闸门会静默失效；"
        "这类「不抛错的失效」比崩溃更危险（异常被自己的 try 吃掉 = 静默放行）")


@pytest.mark.parametrize("data", [DATA_LIST, DATA_DICT], ids=["list_form", "dict_form"])
def test_loc_map_from_element_map_reads_both_forms(tmp_path, data):
    """`_load_loc_map_from_element_map`（定位映射）：两种形态都要建出映射。"""
    from framework.features.f02_semantic.generator_generate import _load_loc_map_from_element_map
    got = _load_loc_map_from_element_map(_write(tmp_path, data))
    assert NAME in got, f"定位映射没建出来（实际 {sorted(got)[:5]}）"
