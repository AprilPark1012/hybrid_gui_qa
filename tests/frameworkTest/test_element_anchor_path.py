"""锚点 + 相对路径契约的判据（一类 · 秒级 · 不需 demo/浏览器）—— P16 批 2「判据先行」。

**背景**：真实系统只有顶层元素有 `data-testid`。框架要能表达「从哪个锚点、沿什么相对路径、找到哪个子元素」，
否则定位只能靠 `data-testid`（demo 现状）或猜 CSS（本项目铁律禁止）。

**本批判据覆盖的契约**（纯函数，可在无浏览器环境下验）：
  · `ElementRef.anchor` / `ElementRef.path` 两个新字段的**序列化往返 + 向后兼容**（老 JSON 没有这两字段）；
  · `anchor.container_from_ancestors()`：从祖先链里挑**最近的可锚定容器**，都锚不住 ⇒ **None（不编造）**；
  · `anchor.path_for_table_row()`：行锚（文本 / 显式行序）+ 列（data-field / 表头文本 / 列序）+ 目标语义；
  · `anchor.header_index()`：无 data-field 时按表头文本取列序（他 2026-09-22 拍的 C 降级路径）。

**红态预期**：本批实现前全红（判据先行）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests" / "frameworkTest"))

from framework.tools.probe.element_map import ElementRef       # noqa: E402


def _anchor_mod():
    import importlib
    return importlib.import_module("framework.tools.probe.anchor")


# ---------------- ① 契约字段：往返 + 向后兼容 ----------------

def test_element_ref_has_anchor_and_path_defaults_none():
    el = ElementRef(semantic_name="contract_no_link")
    assert el.anchor is None and el.path is None


def test_element_ref_roundtrip_keeps_anchor_and_path():
    el = ElementRef(semantic_name="contract_no_link", role="link", name="HT-1001",
                    anchor={"kind": "table", "by": "test_id", "value": "tbl-contracts"},
                    path=[{"axis": "row", "by": "text", "value": "HT-1001"},
                          {"axis": "col", "by": "field", "value": "contractNo"}])
    back = ElementRef.from_dict(json.loads(json.dumps(el.to_dict())))
    assert back.anchor == el.anchor, back.anchor
    assert back.path == el.path, back.path


def test_element_ref_from_old_json_without_new_fields():
    """★ 向后兼容：老生成物 / 老录像里的 ElementRef JSON **没有** anchor/path ⇒ 必须能读、值为 None。"""
    old = {"semantic_name": "search_btn", "role": "button", "name": "搜索", "test_id": "btn-search"}
    el = ElementRef.from_dict(old)
    assert el.semantic_name == "search_btn" and el.test_id == "btn-search"
    assert el.anchor is None and el.path is None, "老 JSON 缺字段必须是 None（不许编造默认锚点）"


def test_element_ref_to_dict_distinguishes_absent_vs_empty():
    """未采集 ≠ 采到空：没有锚就输出 None（下游据此判断"该退化"），不要输出 {} 冒充。"""
    d = ElementRef(semantic_name="x").to_dict()
    assert d["anchor"] is None and d["path"] is None, d


# ---------------- ② 锚点：从祖先链挑最近可锚容器 ----------------

def _anc(tag, **kw):
    return {"tag": tag, **kw}


def test_container_picks_table_with_test_id():
    m = _anchor_mod()
    anc = [_anc("td"), _anc("tr"), _anc("table", test_id="tbl-contracts")]
    a = m.container_from_ancestors(anc)
    assert a == {"kind": "table", "by": "test_id", "value": "tbl-contracts"}, a


def test_container_picks_nearest_when_nested():
    """表格在弹层里 ⇒ 最近的锚点容器是**表格**（不是外层弹层）——下钻范围越小越稳。"""
    m = _anchor_mod()
    anc = [_anc("td"), _anc("table", test_id="tbl-pick-cust"), _anc("div", class_="modal", test_id="modal-new-order")]
    assert m.container_from_ancestors(anc)["value"] == "tbl-pick-cust"


def test_container_supports_dialog_by_aria_label():
    m = _anchor_mod()
    anc = [_anc("input", placeholder="备注"), _anc("div", role="dialog", aria_label="新建采购单")]
    a = m.container_from_ancestors(anc)
    assert a["kind"] == "dialog" and a["by"] == "aria_label" and a["value"] == "新建采购单", a


def test_container_supports_region_by_heading():
    m = _anchor_mod()
    anc = [_anc("input", id="kw-1"), _anc("section", heading="采购单列表")]
    a = m.container_from_ancestors(anc)
    assert a["kind"] == "region" and a["by"] == "heading" and a["value"] == "采购单列表", a


def test_container_returns_none_when_nothing_anchorable():
    """★ 负向：祖先里没有任何可锚信息 ⇒ **None**（宁可不定位，也不编造一个假锚点）。"""
    m = _anchor_mod()
    anc = [_anc("div"), _anc("div"), _anc("body")]
    assert m.container_from_ancestors(anc) is None


def test_container_prefers_test_id_over_weaker_signals():
    """同一容器上多个信号 ⇒ 按 test_id > aria_label > role > heading 取最强的那个。"""
    m = _anchor_mod()
    anc = [_anc("table", test_id="tbl-x", aria_label="采购单列表", heading="采购单")]
    a = m.container_from_ancestors(anc)
    assert a["by"] == "test_id" and a["value"] == "tbl-x", a


# ---------------- ③ 相对路径：行 / 列 / 目标 ----------------

def test_path_row_by_text_then_col_field_then_role():
    m = _anchor_mod()
    p = m.path_for_table_row(row_text="HT-1005", cell_field="contractNo", target_role="link")
    assert p == [{"axis": "row", "by": "text", "value": "HT-1005"},
                 {"axis": "col", "by": "field", "value": "contractNo"},
                 {"axis": "target", "by": "role", "value": "link"}], p


def test_path_col_falls_back_to_header_then_index():
    """无 data-field ⇒ 表头文本；连表头都拿不到 ⇒ 显式列序（1-based）。"""
    m = _anchor_mod()
    assert m.path_for_table_row(row_text="PO-1001", col_header="链接", target_role="link")[1] == \
        {"axis": "col", "by": "header", "value": "链接"}
    assert m.path_for_table_row(row_text="PO-1001", col_index=5, target_role="link")[1] == \
        {"axis": "col", "by": "index", "value": 5}


def test_path_row_index_is_explicit_when_no_text():
    """给不出行文本时，**显式行序**可以（但必须由调用方明确指定，不许默认第 1 行）。"""
    m = _anchor_mod()
    p = m.path_for_table_row(row_index=2, col_header="操作", target_role="button")
    assert p[0] == {"axis": "row", "by": "nth", "value": 2}, p


def test_path_omits_row_step_when_no_anchor_given():
    """★ 负向：既没行文本也没显式行序 ⇒ **不许**生成行步（生成 = 偷偷按第一行猜，正是假通过源头）。"""
    m = _anchor_mod()
    p = m.path_for_table_row(col_header="备注", target_role="textbox")
    assert all(s["axis"] != "row" for s in p), p


def test_path_empty_when_nothing_known():
    m = _anchor_mod()
    assert m.path_for_table_row() == []


# ---------------- ④ 表头列序（无 data-field 的降级）----------------

def test_header_index_finds_column_1_based():
    m = _anchor_mod()
    headers = ["单号", "供应商", "金额", "操作", "链接"]
    assert m.header_index(headers, "链接") == 5
    assert m.header_index(headers, "单号") == 1


def test_header_index_strips_whitespace_and_returns_none_when_missing():
    m = _anchor_mod()
    assert m.header_index([" 金额 ", "操作"], "操作") == 2
    assert m.header_index(["单号"], "不存在") is None, "找不到列 ⇒ None（不许退化成第 1 列）"
    assert m.header_index([], "单号") is None
