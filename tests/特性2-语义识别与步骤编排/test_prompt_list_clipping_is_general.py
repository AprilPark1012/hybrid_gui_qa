# -*- coding: utf-8 -*-
"""特性2 · 喂给 AI 的清单裁剪：**通用能力，不许写死特例**（V8.4.3+）。

三轮同形态事故，都是「按条数切」害的：
    1) `items[:60]`           —— 跨页时第 3 页往后全被截（新建订单页的「客户/销售员」看不见）
    2) `max(8, 60 // 页数)`    —— 页数一多每页只剩 8 个
    3) `max(24, 120 // 页数)`  —— 只是把魔数改大，**复杂页面照样超**（被用户当场指出：
       "碰到复杂页面，控件数量还不只 24 个…要构建通用能力，不能写死特例"）

-> 正确口径不是"数字调多大"，而是**换掉"用条数当预算"这件事本身**：
    · 真实成本是**字符**（条目长短差 10 倍）；
    · 重要性由**内容**决定（场景提到的 + 页面标必填的 -> 无条件全给）；
    · 其余按**页间轮转**填预算 -> 页控件多自然多拿，**不存在"每页几个"**；
    · 裁剪**必须明示**（静默残缺 = AI 在残缺依据上推理）。
"""
import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from framework.tools.explore import explorer as EX   # noqa: E402


def _mk(name, page="页A", role="button", **kw):
    d = {"semantic_name": f"{name}@{page}", "page": page, "role": role,
         "name": name, "text": name, "base_name": name, "nearby_text": name}
    d.update(kw)
    return d


def _big_page(n, page="页A"):
    return [_mk(f"普通控件{i}", page) for i in range(n)]


@pytest.fixture
def budget(monkeypatch):
    """把字符预算调到很小，逼出裁剪路径（默认 90000 太大，测不到边界）。"""
    def _set(chars):
        monkeypatch.setenv("HYBRID_PROMPT_LIST_CHARS", str(chars))
    return _set


# ---------- ① 必给层：永远不因预算被裁 ----------

def test_scenario_mentioned_survive_tiny_budget(budget):
    """【核心通用性】预算再小，**场景原文提到的**控件也必须全给。"""
    budget(4000)
    items = _big_page(200) + [_mk("客户", "新建订单页", ctx_token="*客户"),
                              _mk("销售员", "新建订单页", ctx_token="*销售员")]
    sel = EX.select_controls_for_prompt(items, None, "在新建订单页填写：客户与销售员各选第一个")
    picked = [x for _nm, grp, _h in sel for x in grp]
    names = {x["semantic_name"] for x in picked}
    assert "客户@新建订单页" in names and "销售员@新建订单页" in names, \
        "场景提到的控件被预算裁掉了（这类漏一个就必然失败）"


def test_required_marked_survive_tiny_budget(budget):
    """页面标了必填（`*` 前缀）的控件同样不受预算影响。"""
    budget(4000)
    items = _big_page(200) + [_mk("承运商", "新建订单页", ctx_token="*承运商")]
    sel = EX.select_controls_for_prompt(items, None, "随便写的场景")
    names = {x["semantic_name"] for _nm, grp, _h in sel for x in grp}
    assert "承运商@新建订单页" in names


def test_budget_actually_bites(budget):
    """【反向自证】预算必须真的生效 —— 否则"必给层全给"是假证据（200 条不可能全塞进 4000 字符）。"""
    budget(4000)
    sel = EX.select_controls_for_prompt(_big_page(200), None, "无")
    picked = [x for _nm, grp, _h in sel for x in grp]
    hidden = [h for _nm, _g, h in sel]
    assert sum(hidden) > 0, "预算没生效（200 条都塞进去了）-> 本组判据失去意义"
    assert len(picked) < 200


# ---------- ② 页间轮转：不写死"每页几个" ----------

def test_every_page_gets_representation_when_tight(budget):
    """预算紧张时**每个页都要有份**（不允许前面的页吃光、后面的页颗粒无收）。"""
    budget(4000)
    pages = [{"name": f"页{i}", "url": f"http://x/{i}"} for i in range(6)]
    items = []
    for p in pages:
        items += _big_page(60, p["name"])
    sel = EX.select_controls_for_prompt(items, pages, "无")
    for nm, grp, _h in sel:
        assert grp, f"页面「{nm}」一条控件都没分到（轮转失效 -> 又变成位置决定命运）"


def test_complex_page_gets_more_than_simple_page(budget):
    """控件多的页应拿到**不少于**控件少的页（轮转的自然结果，无需"每页 N 个"配置）。"""
    budget(20000)
    pages = [{"name": "小页", "url": "http://x/1"}, {"name": "复杂页", "url": "http://x/2"}]
    items = _big_page(5, "小页") + _big_page(300, "复杂页")
    sel = dict((nm, grp) for nm, grp, _h in EX.select_controls_for_prompt(items, pages, "无"))
    assert len(sel["复杂页"]) >= len(sel["小页"]), "复杂页拿到的控件反而更少"
    assert len(sel["复杂页"]) > 24, "复杂页仍被一个静态小配额卡住（这就是被指出的问题）"


def test_no_per_page_quota_magic_number_in_code():
    """【防回归】源码里不许再有「每页 N 个」这类配额（断言**剔注释**后，注释骗过判据已犯 4 次）。"""
    src = pathlib.Path(EX.__file__).read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for bad in ("budget_per_page", "items[:60]", "max(8, 60", "max(24, 120"):
        assert bad not in code, f"按条数的配额「{bad}」又回来了 —— 复杂页面必然被截"


# ---------- ③ 压表示：优先于截断 ----------

def test_unique_control_is_compressed():
    """唯一控件压到最小字段集（重复字段、空字段、内部字段全丢）。"""
    it = _mk("客户", role="combobox", placeholder="请选择", ctx_token="*客户",
             label="", test_id="", name_source="x", base_conflict="")
    c = EX._compact_item(it, set())
    assert set(c) <= {"semantic_name", "role", "tag", "placeholder", "ctx_token",
                      "opens_new_tab", "page"}
    assert c["semantic_name"] == "客户@页A" and c["ctx_token"] == "*客户"
    assert len(json.dumps(c, ensure_ascii=False)) < len(json.dumps(it, ensure_ascii=False))


def test_same_named_controls_keep_disambiguation_fields():
    """【与提示词对齐】同名控件必须保留 `nearby_text/visible/container_heading/label`
    —— 提示词明确让 AI 用它们分辨区域，压掉就等于让那句指导失效。"""
    a = _mk("订单名称", "订单列表页", role="textbox", container_heading="查询条件", label="订单名称")
    b = _mk("订单名称", "新建订单页", role="textbox", container_heading="新建弹窗", label="订单名称")
    amb = EX.ambiguous_base_names([a, b])
    assert amb == {"订单名称"}
    ca = EX._compact_item(a, amb)
    assert ca.get("container_heading") == "查询条件" and ca.get("label") == "订单名称"


def test_ambiguous_detection_uses_base_name_not_full_semantic():
    """同名判定要按**字段名**（去 `*`、去 `@页名`），不是按完整语义名
    —— 否则 `订单名称@页A` 与 `订单名称@页B` 会被误判为不同控件。"""
    assert EX.ambiguous_base_names([_mk("订单名称", "页A"), _mk("订单名称", "页B")]) == {"订单名称"}
    assert EX.ambiguous_base_names([_mk("订单名称", "页A"), _mk("客户", "页B")]) == set()


# ---------- ④ 裁剪必须明示 ----------

def test_truncation_is_disclosed(budget):
    """被裁了多少条必须能拿到（静默残缺 = AI 在残缺依据上推理）。"""
    budget(4000)
    sel = EX.select_controls_for_prompt(_big_page(200), None, "无")
    assert sum(h for _n, _g, h in sel) > 0, "裁了却不报条数"


def test_truncation_note_appears_in_prompt(budget):
    """提示词里必须有一句告知「清单是按篇幅裁剪的」。"""
    budget(4000)
    prompt = EX._build_planner_prompt("场景", _big_page(200), "http://x/1", [])
    assert "按篇幅裁剪" in prompt, "裁剪没在提示词里明示"


# ---------- ⑤ 单一入口 + 通用预算工具 ----------

def test_single_page_and_multi_page_share_entry_point():
    """单页/跨页必须走**同一个**选取函数（过去两条路径各写一段，同一 bug 轮流复发）。"""
    src = pathlib.Path(EX.__file__).read_text(encoding="utf-8")
    i = src.index("def _build_planner_prompt(")
    seg = src[i:i + 20000]
    assert seg.count("select_controls_for_prompt(") == 1, \
        "控件清单有多处各自裁剪 -> 又会出现「两条路径不同步」"


def test_clip_by_chars_keeps_order_and_reports_hidden(budget):
    """通用字符裁剪：保序 + 如实报被裁条数。"""
    budget(2000)
    entries = [{"i": i, "pad": "x" * 50} for i in range(100)]
    kept, hidden = EX._clip_by_chars(entries)
    assert hidden > 0 and kept == entries[:len(kept)], "裁剪改了顺序（位置类清单不能重排）"


def test_budget_is_configurable_and_registered(budget):
    """预算必须**可调 + 可发现**（登记在 cli config 的可调项清单里）。"""
    budget(12345)
    assert EX._list_char_budget() == 12345
    from framework.cli import TUNABLE_CATALOG
    assert any(k == "HYBRID_PROMPT_LIST_CHARS" for k, _d, _s in TUNABLE_CATALOG), \
        "预算旋钮没登记 -> 用户翻源码才知道（违反「可调项必须可发现」）"


def test_invalid_budget_falls_back(budget):
    """预算值写错不许崩（退回默认）—— 环境变量是用户手写的。"""
    budget("abc")
    assert EX._list_char_budget() == EX._DEFAULT_LIST_CHARS
