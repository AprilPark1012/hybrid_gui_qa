# -*- coding: utf-8 -*-
"""特性8 · 录像**结构键的稳定性**（V8.4.2 · 端到端实测逼出来的）。

事故（2026-10-09 实测）：
    同一条命令 `explore --ai --llm-cassette` 连跑两次，**一次命中、一次不命中**。
    实测三份录像的差异，不稳定源有三层：

      ① 结构键里含「**唯一化后的语义名**」—— `HT_1001@发票列表页`、`删除_2`、`单位@详细信息`
         唯一化的结果取决于「该名称在哪些页面出现」，而 demo 的**运行期数据**会变
         （跑过测试后多了记录、列表多了行）-> 同一场景、同一页面结构，键却不同。
      ② 严格键里含**场景 yml 原文** -> 场景文案改一个字（补一句 iframe 说明）就整份不命中。
      ③ 两者都含**完整控件清单 + DOM 上下文** -> 每次探测数量都略有差异。

    结论：**结构键的职责是「同一场景 + 同一页面结构」可复用**，那就**不能**掺进
    「这一轮恰好探测到哪些控件 / 它们恰好分布在几页」这种**运行期观测**。

修法（V8.4.2）：
    结构键只取**稳定骨架** —— 场景文案（值归一化后）+ 页面 URL 集合 +
    控件**基础名**（剥掉 `@页名` 后缀与 `_N` 序号）+ role/name/label/placeholder/test_id。
    **不取**：控件数量、跨页唯一化产生的页名后缀、`_N` 序号、DOM 上下文、业务数据值。
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.tools.explore import llm_cassette as lc  # noqa: E402


# ---------------------------------------------------------------- 基础名剥壳

def test_strip_qualifier_only_strips_page_suffix():
    """`strip_qualifier` **只**剥 `@页名`（业务名里不会出现 `@`，剥它绝对安全）。"""
    assert lc.strip_qualifier("HT_1001@发票列表页") == "HT_1001"
    assert lc.strip_qualifier("单位@详细信息") == "单位"
    assert lc.strip_qualifier("订单名称@新建订单页") == "订单名称"
    assert lc.strip_qualifier("保存@应收发票创建@开票页") == "保存"   # 多重 @ 也剥干净
    assert lc.strip_qualifier("订单名称") == "订单名称"
    assert lc.strip_qualifier("搜索") == "搜索"
    assert lc.strip_qualifier("") == ""


def test_strip_qualifier_never_touches_business_number():
    """**红线判据**：`HT_1001` 的 `_1001` 是**业务编号**，绝不能被当序号剥掉。

    [!] 第一版实现用 `_\\d+$` 剥序号，实测把 `HT_1001@发票列表页` 剥成了 `HT`
        —— 所有合同折成同一个控件名，比「不命中」更糟（会命中错的控件）。
    """
    assert lc.strip_qualifier("HT_1001") == "HT_1001"
    assert lc.strip_qualifier("SO_1020@订单列表页") == "SO_1020"
    assert lc.strip_qualifier("HT_1001@发票列表页") != "HT"


def test_element_fingerprint_folds_numbers_and_page_suffix():
    """`element_fingerprint` = 剥 `@页名` + **数字串折成 `<NUM>`**。

    数字串的两类来源都是**探测当时的观测**：
      · 同页重名控件被编号（`删除_2` / `删除_3`）
      · 表格行控件随数据行数变化（`HT_1001` / `HT_1002` / `HT_1030`）
    """
    assert lc.element_fingerprint("删除_2") == lc.element_fingerprint("删除")
    assert lc.element_fingerprint("HT_1001") == lc.element_fingerprint("HT_1002")
    assert lc.element_fingerprint("单位_2@详细信息") == lc.element_fingerprint("单位@详细信息")
    assert lc.element_fingerprint("订单名称@新建订单页") == "订单名称"
    # 不带数字的名字原样保留（这样「冒出全新控件名」仍然能区分）
    assert lc.element_fingerprint("搜索") == "搜索"


# ---------------------------------------------------------------- 稳定性

def _items(*names):
    return [{"page": "P", "semantic_name": n, "role": "button", "name": n, "label": "",
             "placeholder": "", "test_id": "", "opens_new_tab": ""} for n in names]


def test_struct_key_ignores_page_qualifier_variants():
    """**核心判据**：同一个控件因为「多出现在一页」而被唯一定名 -> 结构键**不该变**。

    这是实测事故的最小复现：09-30 那两份 prompt 只差这个，键就不同了。
    """
    k1 = lc.struct_key("场景A", _items("HT_1001@合同列表页", "HT_1001@发票列表页"))
    k2 = lc.struct_key("场景A", _items("HT_1001@合同列表页", "HT_1001@订单列表页",
                                       "HT_1001@发票列表页"))
    assert k1 == k2, "控件「多出现在一页」让结构键变了 -> 跨机器回放必不命中"


def test_struct_key_ignores_index_suffix():
    """同页重复控件被编号（`删除` / `删除_2`）-> 结构键不该变。"""
    k1 = lc.struct_key("场景A", _items("删除@开票页", "删除@发票列表页"))
    k2 = lc.struct_key("场景A", _items("删除@开票页", "删除@发票列表页", "删除_2@详细信息"))
    assert k1 == k2


def test_struct_key_ignores_repeated_rows_of_same_kind():
    """**同类控件因数据行数变化而增减**（表格多了几行）-> 结构键不该变。

    数量是**运行期观测**；结构键要的是「页面结构长什么样」。
    [!] 注意别把「冒出**新的控件名**」也算进这条 —— 那是页面结构变了，**必须**让键变
        （见 test_struct_key_still_reacts_to_new_element_name）。
    """
    k1 = lc.struct_key("场景A", _items("HT_1001@合同列表页", "HT_1002@合同列表页"))
    k2 = lc.struct_key("场景A", _items("HT_1001@合同列表页", "HT_1002@合同列表页",
                                       "HT_1030@合同列表页"))
    assert k1 == k2, "表格行数变化让结构键变了 -> 换个数据状态就不命中"


def test_struct_key_still_reacts_to_new_element_name():
    """**反向自证**：真的**换了页面结构**（冒出全新控件）-> 结构键**必须变**。

    不做这条守门的话，把结构键改成常数也能让上面三条全绿 —— 那是空转。
    """
    k1 = lc.struct_key("场景A", _items("搜索", "重置"))
    k2 = lc.struct_key("场景A", _items("搜索", "重置", "一个全新控件"))
    assert k1 != k2, "新控件被忽略了 -> 结构键退化成常数，等于不校验页面结构"


def test_struct_key_still_reacts_to_scenario_change():
    """场景语义真改了 -> 结构键必须变（红线：宁可报错，不拿旧结论套新场景）。"""
    items = _items("搜索")
    assert lc.struct_key("场景A 点搜索", items) != lc.struct_key("场景A 点删除", items)


def test_struct_key_ignores_business_values_in_scenario():
    """场景里的**数据值**（参数化/字面值）不算结构差异（已有口径，守住别退化）。"""
    items = _items("搜索")
    assert lc.struct_key("输入 '1005' 搜索", items) == lc.struct_key("输入 '{关键词}' 搜索", items)
