"""P16 批 3「定位合成」· 一类判据（纯函数部分，无浏览器 —— 秒级）。

**为什么先写它**（R7 判据先行）：`scope_locate` 的真实验证在二类
（`tests/verify_scope_locate.py`，要真浏览器 + 零 testid 夹具页）。但那条路慢、且失败时
只知道"没定位到"，说不清是**表达式拼错**还是**作用域选错**。所以把「表达式怎么拼」这层
拆成纯函数单独钉住 —— 拼错在这里就红，不用等二类。

**钉住的点（都是"拼错 = 假通过/静默走偏"的高危项）**：
  1. 四种锚点签名（`test_id` / `aria_label` / `heading` / `role`）各拼成什么表达式；
  2. **`by=None`（有容器没埋点）** ⇒ 按 `kind` 取 tag 表达式（真实项目最常见的那种表格）；
  3. 三种列口径（`data-field` → 表头文本 → 显式列序）与**表头算不出列序时必须放弃**（绝不默认第 1 列）；
  4. **不许凭空造行步**：路径里没有行锚 ⇒ 表达式里不许出现 `tbody tr`；
  5. `row.nth` 必须**显式可辨**（"按显式行序定位"要出现在 strategy 里）；
  6. 歧义理由文案必须含「歧义」+「唯一」——二类负向判据（③）靠它识别"如实失败"。

跑法（秒级）：
    cd ~/hybrid_gui_qa && .venv/bin/python -m pytest tests/test_scope_locate_expr.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# 动态导入（**不用静态 import**）：本能力批 3 才落地，静态 import 会让 R9「搬家协议」判据
# （tests/test_import_targets.py）报「import 目标不存在」——那是污染判据、掩盖真正的搬家漏改。
# 也不用 importorskip：skip 不是红态，判据先行要的是**红**。
import importlib

try:
    _MOD = importlib.import_module("framework.tools.probe.scope_locate")
    _ERR = ""
except Exception as e:                                                 # noqa: BLE001
    _MOD = None
    _ERR = f"{type(e).__name__}: {e}"


def _req():
    """取被测模块；未实现 ⇒ 如实失败（这就是批 3 的起点红态）。"""
    if _MOD is None:
        pytest.fail(f"P16 批 3 定位合成未实现（判据先行红态）：{_ERR}")
    return _MOD


def anchor_expr(*a, **k):
    return _req().anchor_expr(*a, **k)


def step_expr(*a, **k):
    return _req().step_expr(*a, **k)


def path_expr(*a, **k):
    return _req().path_expr(*a, **k)


def strategy_for(*a, **k):
    return _req().strategy_for(*a, **k)


def ambiguity_reason(*a, **k):
    return _req().ambiguity_reason(*a, **k)


# ---------------- ① 四种锚点签名 ----------------

def test_anchor_expr_test_id():
    assert anchor_expr({"kind": "table", "by": "test_id", "value": "tbl-contracts"}) == \
        'page.get_by_test_id("tbl-contracts")'


def test_anchor_expr_aria_label_uses_attribute_selector():
    """容器（section/dialog）的 aria-label 不能用 get_by_label —— 那 API 只找表单控件。"""
    expr = anchor_expr({"kind": "region", "by": "aria_label", "value": "工具栏"})
    assert 'aria-label="工具栏"' in expr, f"应拼成属性选择器：{expr}"


def test_anchor_expr_heading_declares_fallback():
    """按 heading 锚表：优先"容器内含该标题"，退化"该标题之后第一个同 tag 容器"（真实页面常见写法）。"""
    expr = anchor_expr({"kind": "table", "by": "heading", "value": "采购单列表"})
    assert "heading" in expr and "采购单列表" in expr
    assert "table" in expr, f"退化路径必须限定容器 tag：{expr}"


def test_anchor_expr_by_none_degrades_to_kind_tag():
    """有容器、没埋点（零 testid 表格）⇒ 按 kind 取 tag；**必须标注要求唯一**。"""
    expr = anchor_expr({"kind": "table", "by": None, "value": None})
    assert expr.strip() == "page.locator(\"table\")", expr
    expr_dlg = anchor_expr({"kind": "dialog", "by": None, "value": None})
    assert "role=dialog" in expr_dlg or "dialog" in expr_dlg, expr_dlg


def test_anchor_expr_unknown_kind_raises_or_none():
    """不认识的 kind 不许悄悄拼成"随便一个容器"——那会定位到别的区块（假通过）。"""
    r = anchor_expr({"kind": "shelf", "by": None, "value": None})
    assert r is None, f"未知容器类型必须放弃，实得：{r!r}"


# ---------------- ② 路径逐级拼接 ----------------

def test_step_expr_row_text():
    base = 'page.get_by_test_id("tbl-contracts")'
    got = step_expr(base, {"axis": "row", "by": "text", "value": "HT-1005"})
    assert got == base + '.locator("tbody tr").filter(has_text="HT-1005")', got


def test_step_expr_row_nth_is_explicit_and_zero_based():
    base = "page.locator(\"table\")"
    got = step_expr(base, {"axis": "row", "by": "nth", "value": 2})
    assert got == base + '.locator("tbody tr").nth(1)', f"1-based 入参 ⇒ 0-based 表达式：{got}"


def test_step_expr_col_field_and_index():
    base = 'page.get_by_test_id("tbl-contracts")'
    assert step_expr(base, {"axis": "col", "by": "field", "value": "contractNo"}) == \
        base + ".locator(\"td[data-field='contractNo']\")"
    assert step_expr(base, {"axis": "col", "by": "index", "value": 3}) == \
        base + '.locator("td").nth(2)'


def test_step_expr_col_header_needs_runtime_index():
    """表头文本 ⇒ 列序必须由运行时读 thead 得到；**没有列序 ⇒ 放弃，绝不默认第 1 列**。"""
    base = 'page.get_by_test_id("tbl-contracts")'
    assert step_expr(base, {"axis": "col", "by": "header", "value": "链接"}) is None, \
        "没有运行时候算出的列序时必须返回 None（不许猜第 1 列）"
    got = step_expr(base, {"axis": "col", "by": "header", "value": "链接"}, col_index=5)
    assert got == base + '.locator("td").nth(4)', got


def test_step_expr_target_role_and_text():
    base = 'page.get_by_test_id("tbl-contracts")'
    assert step_expr(base, {"axis": "target", "by": "role", "value": "link"}) == \
        base + '.get_by_role("link")'
    assert step_expr(base, {"axis": "target", "by": "text", "value": "提交"}) == \
        base + '.get_by_text("提交", exact=True)'


# ---------------- ③ 整条路径：与方案 §4.4 的示例逐字一致 ----------------

def test_path_expr_full_chain_matches_spec_example():
    expr = path_expr(
        {"kind": "table", "by": "test_id", "value": "tbl-contracts"},
        [{"axis": "row", "by": "text", "value": "HT-1005"},
         {"axis": "col", "by": "field", "value": "contractNo"},
         {"axis": "target", "by": "role", "value": "link"}],
    )
    assert expr == ('page.get_by_test_id("tbl-contracts").locator("tbody tr")'
                    '.filter(has_text="HT-1005").locator("td[data-field=\'contractNo\']")'
                    '.get_by_role("link")'), expr


def test_path_expr_without_row_step_never_invents_one():
    """只有 target 的路径（如"容器内的按钮"）**不许**凭空加行步 —— 那会把作用域缩小到 tbody。"""
    expr = path_expr({"kind": "dialog", "by": "test_id", "value": "modal-customer"},
                     [{"axis": "target", "by": "role", "value": "button"}])
    assert expr is not None and "tbody tr" not in expr, expr


def test_path_expr_empty_path_is_anchor_itself():
    expr = path_expr({"kind": "table", "by": "test_id", "value": "tbl-contracts"}, [])
    assert expr == 'page.get_by_test_id("tbl-contracts")'


# ---------------- ④ strategy 与歧义文案（二类负向判据的锚） ----------------

def test_strategy_labels_axes():
    s = strategy_for([{"axis": "row", "by": "text", "value": "HT-1005"},
                      {"axis": "col", "by": "field", "value": "contractNo"},
                      {"axis": "target", "by": "role", "value": "link"}])
    assert "row.text" in s and "col.field" in s and "target.role" in s, s


def test_strategy_marks_explicit_row_order():
    """`row.nth` 走的是"显式行序"，风险不同（表序变了就错）⇒ strategy 里必须一眼看出来。"""
    s = strategy_for([{"axis": "row", "by": "nth", "value": 2}])
    assert "显式行序" in s, s
    s_text = strategy_for([{"axis": "row", "by": "text", "value": "X"}])
    assert "显式行序" not in s_text, "文本行锚不算显式行序"


@pytest.mark.parametrize("axis", ["row", "col"])
def test_ambiguity_reason_wording(axis):
    """二类判据 ③ 断言 reason 含「歧义」或「唯一」⇒ 文案必须稳定带上这两个词之一。"""
    r = ambiguity_reason(axis, "选择", 2)
    assert ("歧义" in r or "唯一" in r), r
    assert "2" in r, f"要把实际命中数写出来（便于定位）：{r}"


def test_ambiguity_reason_includes_axis_and_value():
    r = ambiguity_reason("row", "PO-1001", 3)
    assert "PO-1001" in r, r
