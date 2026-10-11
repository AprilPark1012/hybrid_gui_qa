# -*- coding: utf-8 -*-
"""一类判据：**重复控件信号** `multi_match`（2026-10-10 方案 1+2）。

## 为什么需要（真实缺陷链，全部实测）

干净环境 E2E：AI 用例第 17 步「填第一行物料编码」必然红，报 `Locator.fill` 定位失败。
逐层量出来的真相：

1. 详情页进编辑态 + 新增行后，`get_by_role("textbox", name="物料编码")` 命中 **3 个**（每行一个、
   全部 visible/enabled）-> 只给语义名的定位**必然多匹配**，`_act` 拒绝（拒绝是对的：
   宁可失败也不填错行）。**框架当时没有任何"按行下标"的表达能力** -> 补 `row_index`（见
   `_act_row`，判据在 `test_row_cell_ops.py`）。
2. 补了能力 + 教了提示词，**AI 依然不写 `row_index`** —— 因为它**不可能知道**"这个控件每行一个"
   （清单里只有 1 条、没有任何重复信号）。这是 **DOM 事实**，不该让 AI 猜 -> 框架必须给信号。
3. 信号从哪来：探针在**有数据的单据**上能看到多个同名控件；但旧行为给它们各起一个名字
   （`物料编码@详细信息` / `_2` / `_3`，序号名 = DOM 顺序，项目已定性为脆弱）。-> 收敛成**一条**
   并标 `multi_match: N`。
4. 有了信号还要**送到 AI 眼前**：`_compact_item` 是字段白名单（不放行就等于没做）；且实测
   字段级提示会被长 prompt 稀释（AI 引用了带 `multi_match` 的名字却仍不给行定位）-> 提成
   提示词**第 0 位硬清单** `_multi_match_block`。
5. 生成期必须**拦得住**：引用了重复控件却没给行定位的步骤 -> generate 直接产出显式失败。
   [!] 第一版闸门是**哑的**：`it_map` 是 `steps[].element` + `probe_items` **同名先到先得**，
   前者在前且**没有** `multi_match` -> 闸门永不触发。信号必须从**清单条目**单独取（本文件守它）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.tools.explore import explorer as EX                        # noqa: E402
from framework.tools.generate import generator as G                       # noqa: E402


def _it(name: str, *, ctx: str = "详细信息", tag: str = "input", role: str = "textbox",
        page: str = "订单详情页", **kw) -> dict:
    d = {"semantic_name": name, "help_text": name, "name": name, "ctx_token": ctx,
         "container_heading": ctx, "tag": tag, "role": role, "page": page}
    d.update(kw)
    return d


# ---- V1：收敛（同容器重复 -> 一条 + multi_match）----


def test_same_container_repeats_collapse_into_one_item():
    items = [_it("物料编码") for _ in range(3)]
    EX._collapse_row_repeats(items)
    assert len(items) == 1, f"同容器重复项没有收敛：{len(items)} 条"
    assert items[0]["multi_match"] == 3, f"重复个数记错了：{items[0].get('multi_match')}"
    # 唯一控件**不许**带这个键（否则等于把所有控件都标成重复）
    solo = [_it("订单备注")]
    EX._collapse_row_repeats(solo)
    assert "multi_match" not in solo[0]


def test_different_container_is_not_a_repeat():
    """弹层里的「保存」与工具栏里的「保存」是两个控件 -> 绝不能合并（合了就是把两个当一个）。"""
    items = [_it("保存", ctx="详细信息", tag="button", role="button"),
             _it("保存", ctx="确认弹窗", tag="button", role="button")]
    EX._collapse_row_repeats(items)
    assert len(items) == 2, "不同容器的同名控件被错误合并了"


# ---- V2：信号必须能送到 AI 眼前（白名单放行 + 第 0 位硬清单）----


def test_compact_item_passes_multi_match_to_the_ai():
    out = EX._compact_item(_it("物料编码", multi_match=7))
    assert out.get("multi_match") == 7, (
        "`_compact_item` 是给 AI 清单的字段白名单 —— 不放行 multi_match 等于信号没做")
    assert "multi_match" not in EX._compact_item(_it("订单备注")), "唯一控件不该带这个键"


def test_multi_match_hard_block_is_at_prompt_position_zero():
    block = EX._multi_match_block([_it("物料编码", multi_match=7)])
    assert "物料编码" in block and "7" in block, "硬清单没列出重复控件"
    assert "row_index" in block, "硬清单没告诉 AI 怎么表达行定位"
    # 没有重复控件时不许凭空出现这一块
    assert EX._multi_match_block([_it("订单备注")]) == ""
    # [!] 名字必须来自**送 AI 的那份清单**（唯一化之后的清单），不能用探测期累积的那份 ——
    #     实测：硬清单写了 `物料编码@详细信息`，而 AI 清单里叫 `物料编码@订单详情页` -> AI 对不上号。
    import inspect
    sig = inspect.signature(EX._multi_match_block)
    assert "items" in sig.parameters, "硬清单必须接受「送 AI 的那份清单」作为输入"
    src = (ROOT / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
    assert "_multi_match_block(items)" in src, "prompt 组装处没有把清单传进去（名字会对不上）"
    assert "_OUTPUT_CONTRACT + _multi_match_block(items)" in src, \
        "硬清单没挂在 prompt 第 0 位（字段级提示会被长 prompt 稀释，实测 AI 会忽略）"


# ---- V3：生成期闸门（拦得住 + 判据来源正确）----


def test_gate_refuses_rows_without_row_locator():
    src = (ROOT / "framework" / "tools" / "generate" / "generator.py").read_text(encoding="utf-8")
    assert "缺行定位" in src, "生成期没有拦下「引用重复控件却没给行定位」的步骤"
    i = src.index("_mm = int(_MULTI_MATCH.get(elem)")
    block = src[i:i + 900]
    # [!] 2026-10-10（他选 ①）：判据与措辞搬进了**唯一入口** `element_map.row_scope_violation()`
    #     （explore 的产出校验 + 生成期闸门共用）—— 所以这里改成断言"走了唯一入口"，
    #     措辞本身由 `test_row_scope_violation_is_the_single_source_of_truth` 兜。
    assert "row_scope_violation(st, _mm)" in block, "闸门没走唯一入口（两处各写一份会漂）"
    assert "pytest.fail" in block, "拦下必须是**显式失败**，不许渲染成看着能跑的存根"


def test_gate_signal_comes_from_manifest_not_from_it_map():
    """信号必须从**清单条目**取：`it_map` 同名先到先得，`steps[].element` 在前且没有这个键。"""
    mm = G._multi_match_from_source
    assert callable(mm), "缺少 `_multi_match_from_source`（信号来源）"
    src = (ROOT / "framework" / "tools" / "generate" / "generator.py").read_text(encoding="utf-8")
    assert "_MULTI_MATCH.update(_multi_match_from_source(f, kind))" in src, \
        "信号没有与 loc_map/锚**同源**加载（会用错来源、闸门哑掉）"


def test_row_scope_violation_is_the_single_source_of_truth():
    """判据/措辞只有一处：`element_map.row_scope_violation()`。

    为什么单独锁：今天（2026-10-10）实测过的坑 —— 闸门只在 generate 阶段说话、而重试闭环在
    explore 阶段，**原因到不了 AI 手里**；修法是把判据抽成唯一入口、两个阶段共用。
    两处各写一份的话，措辞会漂、判据会不一致（一边拦一边放）。
    """
    from framework.tools.probe.element_map import row_scope_violation as rsv
    # 重复控件 + 只给语义名 -> 必须给出可改原因
    bad = rsv({"element": "物料编码@订单详情页"}, 3)
    assert bad and "重复出现 3 个" in bad and "row_index" in bad, "重复控件没给行定位必须报"
    # 给了行定位 -> 放行（三种合法形态都要认）
    assert rsv({"element": "物料编码@订单详情页", "row_index": -1}, 3) is None
    assert rsv({"element": "物料编码@订单详情页", "row_text": "全链路-1"}, 3) is None
    assert rsv({"element": "物料编码@订单详情页", "cell_field": "qty"}, 3) is None
    # 不重复 -> 与本判据无关（不能顺手拦掉正常步骤）
    assert rsv({"element": "物料编码@订单详情页"}, 1) is None
    assert rsv({"element": "物料编码@订单详情页"}, None) is None


def test_gate_and_explore_share_the_single_source():
    """生成期闸门 + explore 产出校验**共用**同一个判据函数（不许各写一份）。"""
    gen = (ROOT / "framework" / "tools" / "generate" / "generator.py").read_text(encoding="utf-8")
    exp = (ROOT / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
    assert "row_scope_violation(st, _mm)" in gen, "生成期闸门没走唯一入口"
    assert "_has_row_scope" not in gen, "生成期还留着旧的inline判据（两处各写一份 = 会漂）"
    assert "row_scope_violation(_st, multi_match_of_name(_mm_of, _elem))" in exp, \
        "explore 侧没走唯一入口（或没走「先精确、后退回基础名」的查找）"


def test_explore_collects_row_scope_notes_for_the_retry_loop():
    """explore 必须在**产出成型时**收集「行定位缺失」，且从清单条目取 `multi_match`（同源）。"""
    src = (ROOT / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
    assert "_ROW_SCOPE_NOTES: list[str] = []" in src, "没声明收集清单"
    assert "_ROW_SCOPE_NOTES.clear()" in src, "没无条件清（留旧账 -> 下一轮报上一轮的缺陷）"
    assert 'it.get("multi_match")' in src and "_mm_of" in src, \
        "没从清单条目取 multi_match（另立信号来源 = 会与清单漂）"
    # [!] 名字口径：必须同时认 `semantic_name` 与 `base_name`（唯一化前的基础名）。
    #     2026-10-10 实测：探测期那一刻步骤引用的还是**基础名** -> 只按 semantic_name 查
    #     零重合 -> 判据静默失效（遥测原话：重复控件 10 个、撞上重复控件的 0 个）。
    assert "item_multi_match_map(manifest)" in src, "没用唯一入口建映射表"
    assert "multi_match_of_name(_mm_of, _elem)" in src, "查找没走「先精确、后退回基础名」"


def test_retry_loop_actually_reads_row_scope_notes():
    """闭环接通：`cli._verify_cases_detailed` 必须**读**这份清单，并把它变成给 AI 的要求。

    这条是 ① 的核心断言 —— 只知道收集（清单写了没人读）就等于白收集，
    项目自己就犯过这个（注释原话：「这两个清单只收集没人读 -> 等于白收集」）。
    """
    cli = (ROOT / "framework" / "cli.py").read_text(encoding="utf-8")
    assert '_ROW_SCOPE_NOTES' in cli, "重试闭环没读行定位清单 -> 原因还是到不了 AI 手里"
    assert "row_index" in cli and "刚新增的空行只能用" in cli, "没把「怎么补」写进给 AI 的要求"


def test_both_manifest_exits_enforce_collapse():
    """清单不变量必须落在**每个对外出口**：跨页聚合口 + 清单成型口。

    只在 `_merge_items` 里收敛是不够的 —— 探测是**多轮 + 跨页拼接**的，拼接会把残渣带回来
    （实测：`物料编码_2`/`_3` 与主条目签名**完全相同**却仍在清单里 -> 重复信号只标到一条，
    AI 可能引用到没标的那条）。
    """
    src = (ROOT / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
    assert "_collapse_row_repeats(manifest)" in src, "清单成型口没收敛（落盘的清单会有残渣）"
    # [!] 片 3c（2026-10-12，B1 三合一）：**跨页聚合口的收敛跟着骨架搬到了 `probe/scan_pages.py`**
    #   （原在 explorer 的 `_collect_pages_context` 里）。判据跟着搬 —— **不是放宽**：
    #   两个出口仍然各要一处收敛，只是位置变了。
    sp = (ROOT / "framework" / "tools" / "probe" / "scan_pages.py").read_text(encoding="utf-8")
    assert "_collapse(merged)" in sp, "跨页聚合口没收敛（给 AI 的清单会有残渣）"
    assert "collapse" in sp, "scan_pages 没有 collapse 开关（调用方无法表达该出口要不要收敛）"


def test_collapse_is_actually_wired_into_merge():
    """收敛必须真的接在合并链上（只定义不调用 = 死代码）。"""
    src = (ROOT / "framework" / "tools" / "explore" / "explorer.py").read_text(encoding="utf-8")
    assert "_collapse_row_repeats(out)" in src, "收敛函数没有接进 `_merge_items`"
    i = src.index("_collapse_row_repeats(out)")
    assert src.index("assign_semantic_names(out)") > i, \
        "收敛必须在**命名之前**（否则重复项已被命名成 _2/_3，收敛不掉）"


# ==================== 框架兜底补行定位（方案 ③ · 2026-10-11 V8.4.6） ====================
# 背景：AI（deepseek-flash）稳定不写 `row_index` —— 能力/信号/硬清单/闸门/原因喂回全到位也不写。
# 于是由**框架确定性兜底**：能由用例结构判死的就补，判不出来的照旧红（宁红不猜）。
# 这里锁三件事：① 该补的补对（刚新增行 -> row_index=-1）；② 不该补的**绝不补**（跨页同名误伤 /
# 没有新增行 / 本批已出现过行锚）；③ 引擎真的认 -1（补了但引擎不认 = 假绿）。
def _row_add_step(name="新增行@订单详情页"):
    return {"op": "click", "element": name}


def _fill(name, **kw):
    st = {"op": "fill", "element": name}
    st.update(kw)
    return st


def _real_shape_case():
    """按 AI 用例 `ai_orders_invoice_full_lifecycle_*` 的真实形态造：两批「新增行 + 4 个行内字段」，
    末尾再放**别的页面**的同名控件（开票页的数量/单位）—— 那是跨页误伤的样本。"""
    return [
        {"op": "click", "element": "搜索@订单列表页",
         "row_text": "全链路-X", "cell_field": "orderName"},
        _row_add_step(),
        _fill("物料编码@订单详情页"), _fill("产品编码@订单详情页"),
        _fill("数量@订单详情页"), {"op": "select", "element": "行类型@订单详情页"},
        _row_add_step(),
        _fill("物料编码@订单详情页"), _fill("产品编码@订单详情页"),
        _fill("数量@订单详情页"), {"op": "select", "element": "行类型@订单详情页"},
        _row_add_step("新增行@开票页"),
        {"op": "select", "element": "发票行类型@开票页"},
        _fill("数量@开票页"), {"op": "select", "element": "单位@开票页"},
    ]


def _mm_map():
    """清单侧：只有**订单详情页**的行内控件是重复控件（每行一个）；开票页那几个不是。
    另含基名键（`单位`/`数量`）—— 兜底**不许**按基名兜，那会把别的页面带下水。"""
    return {
        "物料编码@订单详情页": 3, "产品编码@订单详情页": 3,
        "数量@订单详情页": 3, "行类型@订单详情页": 3,
        "单位": 3, "数量": 3,
    }


def test_row_locator_fallback_fills_last_added_row():
    """① 该补的补对：两批各 4 个行内字段 -> 全部 row_index=-1。"""
    from framework.tools.probe.element_map import apply_row_locator_fallback
    steps = _real_shape_case()
    notes = apply_row_locator_fallback(steps, _mm_map())
    names = [n["name"] for n in notes]
    assert len(notes) == 8, f"应补 8 处（两批各 4 个），实际 {len(notes)}: {names}"
    assert all(n["rule"] == "R1_last_added_row" for n in notes), f"规则名不对: {notes}"
    for n in notes:
        assert steps[n["index"]]["row_index"] == -1, "补的必须是 row_index=-1（最后一行）"


def test_row_locator_fallback_is_exact_key_only():
    """② 跨页同名不许被带下水：`数量@开票页`/`单位@开票页` 不是清单精确键 -> 不补。"""
    from framework.tools.probe.element_map import apply_row_locator_fallback
    steps = _real_shape_case()
    apply_row_locator_fallback(steps, _mm_map())
    for st in steps:
        if st.get("element") in ("数量@开票页", "单位@开票页"):
            assert st.get("row_index") is None, \
                f"{st['element']} 被误补了行定位（跨页误伤：补错比不补危险得多）"


def test_row_locator_fallback_refuses_without_row_add():
    """② 没有「新增行」这个前提事实 -> 一处都不许补（否则会盖住真缺陷）。"""
    from framework.tools.probe.element_map import apply_row_locator_fallback
    steps = [_fill("物料编码@订单详情页"), _fill("产品编码@订单详情页")]
    assert apply_row_locator_fallback(steps, _mm_map()) == [], "没有新增行却补了"
    assert steps[0].get("row_index") is None


def test_row_locator_fallback_stops_after_explicit_anchor():
    """② 本批一旦出现过行锚就不许再兜底（那时「是不是同一行」已经说不准）。"""
    from framework.tools.probe.element_map import apply_row_locator_fallback
    steps = [
        _row_add_step(),
        _fill("物料编码@订单详情页", row_text="全链路-X", cell_field="materialCode"),
        _fill("产品编码@订单详情页"),
    ]
    notes = apply_row_locator_fallback(steps, _mm_map())
    assert notes == [], f"出现行锚后仍在兜底（会把不同行混在一起）: {notes}"
    assert steps[2].get("row_index") is None


def test_row_locator_fallback_shares_the_scope_field_catalog():
    """③ 字段口径只有一处：判据与兜底都读 `ROW_LOCATOR_FIELDS` / `has_row_locator`。"""
    src = (ROOT / "framework" / "tools" / "probe" / "element_map.py").read_text(encoding="utf-8")
    assert "ROW_LOCATOR_FIELDS" in src and "def has_row_locator" in src
    assert 'step_get(step, "row_text") or step_get(step, "row_index")' not in src, \
        "判据里又内联写了一份字段清单（口径分裂 -> 日后只改一处）"


def test_engine_supports_last_row_index():
    """③ 引擎必须真的认 `row_index = -1`（否则兜底补出来的是假绿）。"""
    src = (ROOT / "scripts" / "generated" / "_harness.py").read_text(encoding="utf-8")
    assert "_act_row" in src and "row_index" in src, "harness 里没有按行定位的执行入口"
    assert "-1` = 最后一行" in src or "-1 = 最后一行" in src, "harness 没写明 -1 的语义"
