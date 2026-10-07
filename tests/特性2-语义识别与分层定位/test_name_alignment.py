"""元素名对齐（explorer._match_item）的契约测试 —— 秒级、不需要浏览器/demo/LLM。

为什么单独立一份：对齐规则是「AI 产出能不能落地」的咽喉，放宽一点就会**静默匹配到错的控件**
（比未映射更糟：未映射会大声告警，错映射点下去就错了）。这里把踩过的坑钉成判据。

2026-09-17 实测的两个坑：
  ① 分页按钮就叫 `1`/`2`/`3` ⇒ 反向包含（清单名是 AI 名字的子串）把
     `选择@HT-1001 → 选择@HT_1001` 判成歧义（该对齐的没对齐）；
  ② 同一个反向包含又会把 `选择客户@新建订单` 匹配成 `新建订单`（**不该对齐的错了**）。
⇒ 规则：先判「规范化后完全相等」；反向包含必须够长（≥3 且 ≥60% 长度）、且
   AI 名字里带 `@`（指定了区域/页面变体）时只接受同样带 `@` 的候选。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from framework.tools.explore.explorer import (_build_planner_prompt, _field_identity, _match_item,      # noqa: E402
                                _same_field_pairs, _shadowed_names)


def _items(*names):
    return [{"semantic_name": n} for n in names]


def test_normalized_equality_beats_pagination_noise():
    """HT-1001 vs HT_1001 只是书写差异 ⇒ 必须对齐（不能被分页按钮 `1` 搅成歧义）。"""
    it, how = _match_item("选择@HT-1001", _items("1", "2", "3", "选择@HT_1001"))
    assert it and it["semantic_name"] == "选择@HT_1001", how


def test_ai_name_with_suffix_never_matches_bare_fragment():
    """AI 写了带 @ 的名字，就绝不允许落到不带 @ 的片段上（会点错控件）。"""
    it, how = _match_item("选择客户@新建订单", _items("新建订单", "选择客户@订单系统"))
    assert it is None, f"错映射：{it}（{how}）—— 未命中要好过点错"


def test_bare_name_aligns_to_unique_prefixed_item():
    """AI 只写了前半段、而清单里只有一个带后缀的版本 ⇒ 可以对齐（唯一才允许）。"""
    it, how = _match_item("订单备注", _items("订单备注_可不填", "订单名称_全模糊"))
    assert it and it["semantic_name"] == "订单备注_可不填", how


def test_ambiguous_bare_name_is_not_guessed():
    """同一个前半段在清单里有两个区域版本 ⇒ 不许猜，判未命中（由调用方大声告警）。"""
    it, how = _match_item("选择@北京华信科技有限公司",
                         _items("选择@北京华信科技有限公司@订单系统",
                                "选择@北京华信科技有限公司@合同列表页"))
    assert it is None, f"两个页面版本都存在时不许猜，实际匹配到 {it}（{how}）"


def test_exact_name_wins():
    it, how = _match_item("搜索@订单系统", _items("搜索@订单系统", "搜索@合同列表页"))
    assert it and how == "精确"


def test_shadowed_names_lists_intra_page_dupes():
    """同一页不同区域的重名（带 @ 区域后缀、且前半段自身也是控件名）必须能被列出来提醒 AI。"""
    pairs = _shadowed_names(_items("选择业务单元", "选择业务单元@新建订单",
                                   "搜索", "选择@HT_1001"))
    assert ("选择业务单元", "选择业务单元@新建订单") in pairs
    assert all(p != "选择" for p, _n in pairs), "行内「选择@X」不算同名陷阱（前缀不是控件名）"


# ---------------------------------------------------------------- 同字段·不同区域·不同名字
# 2026-09-18 实测（订单场景 AI 端到端连跑 6 次、6 次全错）：
#   筛选区的 `订单名称_全模糊`（label=订单名称, container_heading=空）与
#   新建弹窗里的 `请输入订单名称`（label=订单名称 *, container_heading=新建订单）
#   **名字完全不同** ⇒ `_shadowed_names` 报不出来；AI 一律选了「字面最像人话描述」的筛选区那个，
#   因为名字真实存在，generate 不报未映射 ⇒ **静默错映射**（提交后弹窗字段仍为空 ⇒ 首行断言假红）。
# ⇒ 框架必须把这类歧义显式摊在提示词里（`_same_field_pairs`）。

def _field_items():
    return [
        {"semantic_name": "订单名称_全模糊", "label": "订单名称", "placeholder": "订单名称（全模糊）",
         "name": "", "container_heading": ""},
        {"semantic_name": "请输入订单名称", "label": "订单名称 *", "placeholder": "请输入订单名称",
         "name": "", "container_heading": "新建订单"},
        {"semantic_name": "搜索", "label": "", "placeholder": "", "name": "搜索",
         "container_heading": ""},
    ]


def test_same_field_pairs_flags_filter_vs_modal_input():
    """同一个「订单名称」字段、两个区域、两个名字 ⇒ 必须被列出来（含两个名字与所属区域）。"""
    pairs = _same_field_pairs(_field_items())
    assert len(pairs) == 1, pairs
    ident, a, b, detail = pairs[0]
    assert ident == "订单名称", ident
    assert "订单名称_全模糊" in detail and "请输入订单名称" in detail, detail
    assert "新建订单" in detail, "必须给出区域，AI 才能按区域选"


def test_same_field_pairs_ignores_exact_same_name_two_regions():
    """完全同名（选择业务单元 vs 选择业务单元@新建订单）是 `_shadowed_names` 的活，别重复报。"""
    items = [{"semantic_name": "选择业务单元", "label": "选择业务单元", "container_heading": ""},
             {"semantic_name": "选择业务单元@新建订单", "label": "选择业务单元",
              "container_heading": "新建订单"}]
    assert _same_field_pairs(items) == []


def test_same_field_pairs_ignores_same_region_variants():
    """同一区域里两个同名控件（如弹层多次探测）不算陷阱 —— 只报「跨区域」的歧义，别制造噪声。"""
    items = [{"semantic_name": "请输入订单名称", "label": "订单名称", "container_heading": "新建订单"},
             {"semantic_name": "订单名称_x", "label": "订单名称", "container_heading": "新建订单"}]
    assert _same_field_pairs(items) == []


def test_field_identity_normalizes_required_mark_and_placeholder_hint():
    """「订单名称 *」「订单名称（全模糊）」的身份都应是「订单名称」（否则报不出同一字段）。"""
    assert _field_identity({"label": "订单名称 *"}) == "订单名称"
    assert _field_identity({"label": "订单备注（选填）"}) == "订单备注"
    assert _field_identity({"label": "", "placeholder": "订单名称（全模糊）"}) == "订单名称"


def test_prompt_discloses_same_field_pairs():
    """接线判据：提示词里必须真的出现这段歧义披露（否则等于功能没生效，只看函数单测会假绿）。"""
    prompt = _build_planner_prompt("在新建订单弹窗里填写订单名称", _field_items(),
                                   "http://localhost:8000/orders.html")
    assert "同一个字段有多个不同名字的版本" in prompt
    assert "请输入订单名称" in prompt and "订单名称_全模糊" in prompt
    assert "2c." in prompt, "规则里也要有对应条款（否则只是清单里多了一段无解释的告警）"
