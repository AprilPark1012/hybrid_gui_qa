# -*- coding: utf-8 -*-
"""一类判据：**行区信号 `row_zone`**（2026-11-03 · L37）。

## 这道闸防的是什么

用户 Windows 真机实测（`V8.9.1-RUNLOG-11031402.txt`，真 AI 链路）：

    [TEST] [step 55] select → 期次号
    RuntimeError: 定位失败：本页有 **2 个同名匹配**（期次号）
    → 第 1 轮试跑 FAILED 424.9s，靠「带原因重试」第 2 轮才 PASSED 399.1s

根因不是模型不听话，是**探针的观测时机**：

    开票页探测时只有 **1 行**  → 期次号/发票行类型/数量/单位 全部 multi_match=1
                                 → AI 清单里看着唯一、生成期闸门也不拦
    AI 用例自己点「新增行」    → 运行期 2 行 → 2 个同名匹配 → 定位失败

探针能看到的**确定性结构事实**是「该容器里有一个『新增行』动作 -> 这个区必然会长多行」，
与当前行数无关。`row_zone` 就是把这条事实提前说出去，让 AI 第一轮就给行定位，
并让框架兜底在「能判死」时补上 `row_index=-1`，不再白跑 400+ 秒。

## 口径（判据就是按它们写的，改口径必须同步改判据）

1. 只标**输入类**（`保存/取消/新增行` 随行增长也不会变成「第几行的保存」，标它们＝误伤）
2. 只标**当前唯一**的（`multi_match>1` 已有更强信号）
3. **不动 `multi_match`**（写它会让质量闸在单行场景误拦，2026-10-29 已定）
4. 跨页同名控件**不给纯基名**（2026-10-11 栽过：基名兜底把开票页信号套到详情页那步上，补出错的 `row_index`）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.features.f02_semantic.explorer_explore import mark_row_zone, _multi_match_block  # noqa: E402
from framework.features.f03_locate.element_map import (                                        # noqa: E402
    apply_row_locator_fallback, row_zone_names, row_zone_violation)
from framework.features.f05_layers.probe_snapshot_generate import _KEEP                        # noqa: E402


def _item(name, tag="input", role="textbox", page="开票页", heading="发票行", **kw):
    d = {"semantic_name": name, "help_text": name, "tag": tag, "role": role,
         "page": page, "container_heading": heading, "ctx_token": heading}
    d.update(kw)
    return d


def _row_zone_fixture():
    return [
        _item("新增行", tag="button", role="button"),
        _item("保存", tag="button", role="button"),
        _item("期次号", tag="select", role="combobox"),
        _item("数量"),
        _item("客户", heading="基础信息"),          # 不同容器：区内没有新增行 -> 不该被标
    ]


# ---------------------------------------------------------------- ① 标记口径

def test_marks_unique_inputs_in_row_zone_only():
    items = _row_zone_fixture()
    hit = mark_row_zone(items)
    got = {nm for names in hit.values() for nm in names}
    assert got == {"期次号", "数量"}, f"[NG] 打标名单不对: {hit}"
    by = {i["semantic_name"]: i for i in items}
    assert by["期次号"].get("row_zone") is True
    assert by["数量"].get("row_zone") is True, "[NG] 输入类落标了"


def test_does_not_mark_buttons():
    """按钮不标 —— 这是「宁漏不误伤」的核心：给「保存」补行定位会把步骤改错。"""
    items = _row_zone_fixture()
    mark_row_zone(items)
    by = {i["semantic_name"]: i for i in items}
    assert not by["新增行"].get("row_zone"), "[NG] 行增删动作本身被标了"
    assert not by["保存"].get("row_zone"), "[NG] 容器级按钮被标了"


def test_does_not_mark_outside_row_zone():
    """别的容器（没有新增动作）不许沾光。"""
    items = _row_zone_fixture()
    mark_row_zone(items)
    assert not {i["semantic_name"]: i for i in items}["客户"].get("row_zone")


def test_keeps_multi_match_untouched():
    """已有 `multi_match>1` 的不重复标，且**不许**改写 multi_match（写它会误拦单行场景）。"""
    items = [_item("新增行", tag="button", role="button"), _item("数量", multi_match=3)]
    hit = mark_row_zone(items)
    assert hit == {}, f"[NG] 已有强信号的还被打标: {hit}"
    assert items[1]["multi_match"] == 3, "[NG] multi_match 被改写了"


def test_idempotent():
    items = _row_zone_fixture()
    first = mark_row_zone(items)
    second = mark_row_zone(items)
    assert first == second, "[NG] 重复调用结果不一致（不幂等）"
    assert len(items) == 5, "[NG] 条目数变了（标记只该原地打旗标）"


# ---------------------------------------------------------------- ② 名字形态

def test_row_zone_names_single_page_gives_base_name():
    names = row_zone_names([_item("期次号", row_zone=True)])
    assert "期次号" in names and "期次号@开票页" in names


def test_row_zone_names_cross_page_does_not_give_base_name():
    """跨页同名（数量在详情页、开票页各一个）不许给纯基名 —— 否则会补错页。"""
    items = [_item("数量", row_zone=True, page="开票页"),
             _item("数量", page="订单详情页")]
    names = row_zone_names(items)
    assert "数量@开票页" in names
    assert "数量" not in names, "[NG] 跨页同名仍给了纯基名 -> 会把信号套到别的页面"


# ---------------------------------------------------------------- ③ 兜底

def test_fallback_fills_row_index_for_row_zone_after_add_row():
    items = [_item("新增行", tag="button", role="button", row_zone=False),
             _item("期次号", tag="select", row_zone=True),
             _item("保存", tag="button", role="button")]
    rz = row_zone_names(items)
    steps = [{"op": "click", "element": "新增行@开票页"},
             {"op": "select", "element": "期次号@开票页"},
             {"op": "click", "element": "保存@开票页"}]
    fb = apply_row_locator_fallback(steps, {}, rz)
    assert [x["name"] for x in fb] == ["期次号@开票页"], f"[NG] 兜底清单不对: {fb}"
    assert steps[1]["row_index"] == -1
    assert "row_index" not in steps[2], "[NG] 按钮也被补了行定位（误伤）"


def test_fallback_needs_a_row_add_step():
    """前面没有「新增行」动作时不许补 —— R1 的前提事实不成立，补了就是猜。"""
    rz = row_zone_names([_item("期次号", row_zone=True)])
    steps = [{"op": "select", "element": "期次号"}]
    assert apply_row_locator_fallback(steps, {}, rz) == []
    assert "row_index" not in steps[0]


def test_fallback_respects_existing_row_anchor():
    """新增之后已给过行锚 -> 这一批不再兜底（那几步填的是不是同一行说不准，宁红不猜）。"""
    rz = row_zone_names([_item("期次号", row_zone=True)])
    steps = [{"op": "click", "element": "新增行"},
             {"op": "fill", "element": "数量", "row_text": "某行锚"},
             {"op": "select", "element": "期次号"}]
    assert apply_row_locator_fallback(steps, {}, rz) == []
    assert "row_index" not in steps[2]


# ---------------------------------------------------------------- ④ 提示词 + 快照

def test_prompt_block_renders_when_only_row_zone_exists():
    """整页「探测时全都唯一、但区里有新增行」是完全正常的（开票页初始 1 行）——
    那时没有 multi_match，若在早退条件里 return，这一段永远出不来 = 白改。"""
    items = [dict(_item("期次号", tag="select", row_zone=True), multi_match=None),
             dict(_item("新增行", tag="button", role="button"), multi_match=None)]
    blk = _multi_match_block(items)
    assert "行区控件" in blk, "[NG] 只有 row_zone 时提示词段没产出"
    assert "期次号" in blk


def test_prompt_block_empty_when_nothing():
    assert _multi_match_block([_item("客户")]) == ""


def test_row_zone_survives_snapshot_whitelist():
    """`row_zone` 必须进运行时快照白名单 —— 丢了的话 generate 期拿不到信号（白名单漏字段=静默失效）。"""
    assert "row_zone" in _KEEP, "[NG] _KEEP 漏了 row_zone：快照落盘会把它丢掉"


# ---------------------------------------------------------------- ⑤ 警告措辞（不许谎报）

def test_row_zone_violation_does_not_claim_duplicates():
    """探测时它确实只有 1 个 —— 措辞里**不许**出现「重复出现 N 个」那种假话。

    「不许编造」是底线：`row_scope_violation` 说「重复 N 个」是因为它手上真有 N；
    行区信号手上只有 1，只能说「会随行增长、运行期可能同时命中多个」。
    """
    rz = row_zone_names([_item("期次号", row_zone=True)])
    reason = row_zone_violation({"op": "select", "element": "期次号"}, rz)
    assert reason, "[NG] 该报的没报"
    assert "重复出现" not in reason, f"[NG] 谎报了重复个数: {reason}"
    assert "row_index" in reason, "[NG] 没给出可改的做法"


def test_row_zone_violation_silent_when_row_locator_present():
    rz = row_zone_names([_item("期次号", row_zone=True)])
    assert row_zone_violation({"op": "select", "element": "期次号", "row_index": 1}, rz) is None


def test_row_zone_violation_silent_outside_row_zone():
    rz = row_zone_names([_item("期次号", row_zone=True)])
    assert row_zone_violation({"op": "fill", "element": "客户"}, rz) is None


# ---------------------------------------------------------------- ⑥ 去重键（真机踩过的坑）

def test_row_zone_dedupe_uses_step_name_of():
    """去重键必须走**唯一入口** `step_name_of()`。

    实测事故（2026-11-03）：去重代码写了但警告仍是 6 条 —— 因为 steps 里的 `element` 可能是
    `ElementRef`，`str(step_get(...))` 拿到的是 `repr`（`ElementRef(semantic_name='数量@开票页')`），
    与行区循环里的干净名字对不上，`in _mm_noted` 永远为假 = 去重静默失效。
    """
    src = (ROOT / "framework" / "features" / "f02_semantic" / "explorer_explore.py").read_text(encoding="utf-8")
    i = src.index("_mm_noted")
    j = src.index("if _ROW_SCOPE_NOTES:", i)
    seg = src[i:j]
    assert "step_name_of(_st)" in seg, "[NG] 去重键没走 step_name_of"
    assert '_mm_noted.add(_nm_mm)' in seg, "[NG] 记录去重名的方式变了"
    assert 'str(step_get(_st, "element") or "")' not in seg, (
        "[NG] 又用 str(step_get(...)) 当键 —— ElementRef 会变成 repr，去重静默失效")
