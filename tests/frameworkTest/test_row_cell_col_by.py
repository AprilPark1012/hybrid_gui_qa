"""一类判据：行内定位的「列」支持多种指定方式（2026-09-30，P22 批 5）。

## 为什么需要（真实缺陷，可复现）

跨角色链路最后一段要**勾选订单行**再点「去开票」。用例本来写 `cell_field: "pick"`，
但 demo 的勾选列**根本没有 `data-field`**（它是 `<td class="pick-cell">` + `input.ord-pick`），
表头 `<th class="pick-head">` 也**没有文本** ⇒ 既不能按 field 也不能按 header 定位。

```
RuntimeError: 行内列 'pick' 定位失败：列「pick」未命中（0 个）⇒ 无把握，不猜
```

⇒ `scope_locate` 的 col 轴本来就支持 field / header / index 三种，但**用例侧只能表达 field**
  ⇒ 补一个 `cell_by` 字段把另外两种暴露出来。

## 判据口径

- `cell_by` 缺省 = `field`（**既有用例/生成物零改动**，见 V3）。
- 白名单：field / header / index。非法值 ⇒ 生成期失败，不许静默按 field 处理。
- `cell_by: index` ⇒ 用 `cell_index`（0 基）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from framework.tools.generate.generator import (  # noqa: E402
    _CELL_BY_WHITELIST,
    _is_row_cell_step,
    _row_col_step,
)

GEN_SRC = (ROOT / "framework" / "tools" / "generate" / "generator.py").read_text(encoding="utf-8")


# ---- V1：白名单 ----


def test_cell_by_whitelist():
    assert set(_CELL_BY_WHITELIST) == {"field", "header", "index"}, _CELL_BY_WHITELIST


# ---- V2：三种方式都能产出正确的 locate step ----


def test_field_is_default():
    """不给 cell_by ⇒ 按 field（与改造前一致）。"""
    st = _row_col_step("orderNo", None, None)
    assert st == {"axis": "col", "by": "field", "value": "orderNo"}, st


def test_header_mode():
    st = _row_col_step("状态", "header", None)
    assert st == {"axis": "col", "by": "header", "value": "状态"}, st


def test_index_mode_uses_cell_index():
    """index 方式 ⇒ value 取 cell_index（数字）。口径 **1 基**（第 1 列 = 1）。"""
    st = _row_col_step(None, "index", 1)
    assert st == {"axis": "col", "by": "index", "value": 1}, st


def test_index_is_one_based():
    """★ 实测踩过：本以为是 0 基、传了 0 ⇒ 下游 `.nth(-1)` 取到**最后一列**，
    报错却是 "Not a checkbox"（看着像另一个问题）。这里守死 1 基 + 非法值必拦。"""
    assert _row_col_step(None, "index", 1)["value"] == 1
    for bad in (0, -1):
        try:
            _row_col_step(None, "index", bad)
        except ValueError as e:
            assert "从 1 起" in str(e) or "1" in str(e)
        else:
            raise AssertionError(f"cell_index={bad} 必须报错（否则静默取到最后一列）")


def test_index_mode_requires_cell_index():
    """声明 index 却没给 cell_index ⇒ 生成期报错（不许产出无效 step）。"""
    try:
        _row_col_step("x", "index", None)
    except ValueError as e:
        assert "cell_index" in str(e)
    else:
        raise AssertionError("cell_by=index 但没有 cell_index ⇒ 必须报错")


def test_illegal_cell_by_raises():
    try:
        _row_col_step("x", "css", None)
    except ValueError as e:
        assert "css" in str(e)
    else:
        raise AssertionError("非法 cell_by 必须报错（否则会静默当 field 用）")


# ---- V3：既有生成物兼容（回归护栏）----


def test_runtime_keeps_field_default():
    """运行期不传 cell_by ⇒ 仍按 field（已有生成物零改动可跑）。"""
    # 口径收敛到 `_row_col_step` 这一个构造器后，断言应当验**行为**而不是字面串：
    assert _row_col_step("orderNo", None, None) == {"axis": "col", "by": "field", "value": "orderNo"}
    m = re.search(r'def _click_row_cell\(.*?\n(?=\ndef |\nclass )', GEN_SRC, re.S)
    assert m is not None, "找不到运行期实现"
    assert "_row_col_step(" in m.group(0), \
        "运行期没走统一构造器 ⇒ 生成期与运行期的列口径会各写一份（漂移风险）"


# ---- V4：用 cell_by 的行内步不能被映射质量闸误拦（假红护栏）----


def test_row_cell_step_recognizes_cell_by():
    """★ 实测过的坑：勾选列改用 `cell_by=index` 后，闸门（只认 cell_field）把这一步判成
    「没有 element」⇒ 直接拒绝产出任何产物。这里两侧都守住。"""
    assert _is_row_cell_step({"row_text": "X", "cell_field": "orderNo"}) is True
    assert _is_row_cell_step({"row_text": "X", "cell_by": "index",
                              "cell_index": 0}) is True, \
        "用 cell_by 的行内步被当成「没有 element」⇒ 质量闸会拒绝产出（实测踩过）"
    assert _is_row_cell_step({"row_text": "X", "cell_by": "header", "cell_field": "状态"}) is True
    # 负向：没有行锚 / 两种列指定都没有 ⇒ 不算行内步（该被闸门拦下，这才是它该拦的）
    assert _is_row_cell_step({"row_text": "X"}) is False
    assert _is_row_cell_step({"cell_field": "orderNo"}) is False
    assert _is_row_cell_step({}) is False


def test_render_and_gate_share_one_predicate():
    """渲染分支与质量闸必须**共用**这一个判定（否则又会各写一份、再漂移）。"""
    assert GEN_SRC.count("_is_row_cell_step(st)") >= 2, \
        "渲染分支与质量闸没有共用 _is_row_cell_step ⇒ 两条路径会再次漂移"
    assert 'st.get("row_text") and st.get("cell_field")' not in GEN_SRC, \
        "还有地方在按老口径硬判行内步（只认 cell_field）"


# ---- V5：生成期与**运行期模板**必须同口径（否则运行时 NameError）----


def test_runtime_template_has_row_col_step():
    """★ 实测踩过：构造器只加在 generator 里、没进 `_harness.py` 模板 ⇒
    运行时报 `NameError: name '_row_col_step' is not defined`（生成物里没有它）。
    模板是**渲染进生成物**的那份源码，必须自带这个函数与白名单。"""
    m = re.search(r'def _click_row_cell\(.*?\n(?=\ndef |\nclass )', GEN_SRC, re.S)
    assert m, "找不到运行期实现"
    # 模板区域里（_click_row_cell 之前）必须有定义
    before = GEN_SRC[:m.start()]
    assert "def _row_col_step(" in before, "运行期模板里没有 _row_col_step 定义 ⇒ 生成物会 NameError"
    assert '_CELL_BY_WHITELIST = ("field", "header", "index")' in before, \
        "运行期模板里缺 _CELL_BY_WHITELIST ⇒ 生成物会 NameError"
    # 两处口径必须字面一致（防漂移）
    gen_def = re.search(r'_CELL_BY_WHITELIST = \([^)]*\)', GEN_SRC).group(0)
    assert GEN_SRC.count(gen_def) >= 2, "生成期与运行期的白名单口径不一致（应该逐字相同）"


def test_no_hardcoded_field_only_in_runtime():
    """运行期 col step 的 by 必须来自参数，不能写死 field。"""
    m = re.search(r'def _click_row_cell\(.*?\n(?=\ndef |\nclass )', GEN_SRC, re.S)
    body = m.group(0)
    assert "cell_by" in body, "运行期没有接收 cell_by ⇒ 生成期传了也没用"
