# -*- coding: utf-8 -*-
"""行按**唯一标识**定位（`tr[data-rowid="row_1"]`）—— V8.8.0 P0-C。

为什么需要
----------
框架原来的行锚只有两档：

    row_text（行内唯一文本） > row_index（第几行）

两者的失效场景都很具体：
  · `row_text` —— 行内文本重复（同为「待处理」的两行）就歧义；
  · `row_index` —— 行序一变（新增 / 删除 / 排序）直接指错行。

真实生产系统的行标识是前端框架生成的行唯一值（`data-rowid="row_1"`），
**值稳定、与行序无关** —— 这才是最稳的一档。优先级因此变成：

    row_id > row_text > row_index

判据口径
--------
1. `TestStep` 必须有 `row_id` 字段，且 **`to_dict` / `from_dict` 都透传**
   （一处加六处查：构造 -> TestStep -> to_dict -> 透传 -> 质量闸 -> 清单防截断；
   漏一处就**静默丢失**，这正是以前踩过的坑）；
2. `path_for_table_row` 的优先级必须是 `row_id` > `row_text` > `row_index`；
3. 执行层（`step_expr`）必须支持 `by: id`，且**属性名同样不写死**；
4. 探测层（`_table_context`）必须把推断出的 `row_attr` 传进去；
5. `Playwright locator.evaluate` 只收一个 arg —— 多传会被 `except` 吞掉，
   表现为「有 row_id 却不走行内定位」的静默失效。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EM = ROOT / "framework" / "features" / "f03_locate" / "element_map.py"
ANCHOR = ROOT / "framework" / "features" / "f03_locate" / "anchor_locate.py"
SCOPE = ROOT / "framework" / "features" / "f03_locate" / "scope_locate.py"
PROBE = ROOT / "framework" / "features" / "f03_locate" / "probe.py"


def _src(p: Path) -> str:
    assert p.is_file(), f"找不到 {p}"
    return p.read_text(encoding="utf-8")


def _func_src(p: Path, name: str) -> str:
    src = _src(p)
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return ast.get_source_segment(src, n) or ""
    raise AssertionError(f"{p.name} 里找不到 {name}")


# ---------------------------------------------------------------- 1) 透传链
def test_teststep_has_row_id_field():
    body = _func_src(EM, "__init__") if False else _src(EM)
    assert "row_id: str | None = None" in body, (
        "`TestStep` 没有 `row_id` 字段 —— AI 想用行标识也表达不了")


def test_row_id_survives_to_dict():
    """用**真对象**验证，不扫文本 —— `to_dict` 走的是 `asdict`，手写键名早就改了。"""
    from framework.features.f03_locate.element_map import TestStep

    s = TestStep(order=1, op="click", row_id="row_7")
    d = s.to_dict()
    assert "row_id" in d, f"`to_dict` 的输出里没有 row_id -> 落盘静默丢失：{sorted(d)}"
    assert d["row_id"] == "row_7", d


def test_row_id_survives_from_dict():
    from framework.features.f03_locate.element_map import TestStep

    s = TestStep.from_dict({"order": 1, "op": "click", "row_id": "row_7"})
    assert s.row_id == "row_7", f"`from_dict` 丢了 row_id：{s.row_id!r}"


def test_to_dict_and_from_dict_are_symmetric():
    """加了字段就必须两边都加 —— 这是「一处加六处查」里最容易漏的一对。"""
    from framework.features.f03_locate.element_map import TestStep

    s = TestStep(order=1, op="click", row_text="x", cell_field="c", cell_by="field",
                 cell_index=2, row_index=3, row_id="r")
    d = s.to_dict()
    back = TestStep.from_dict(d)
    for f in ("row_text", "cell_field", "cell_by", "cell_index", "row_index", "row_id"):
        assert f in d, f"`to_dict` 缺 {f}"
        assert getattr(back, f) == getattr(s, f), f"往返一趟 {f} 变了：{getattr(s, f)!r} -> {getattr(back, f)!r}"


# ---------------------------------------------------------------- 2) 优先级
def test_row_id_has_highest_priority():
    body = _func_src(ANCHOR, "path_for_table_row")
    i_id = body.find('by": "id"')
    i_text = body.find('by": "text"')
    assert i_id != -1, "`path_for_table_row` 没有产出 by=id 的行步"
    assert i_id < i_text, (
        "row_id 必须排在 row_text **之前**判断 —— 否则永远轮不到它（优先级形同虚设）")


def test_row_index_is_last_resort():
    body = _func_src(ANCHOR, "path_for_table_row")
    i_text = body.find('by": "text"')
    i_nth = body.find('by": "nth"')
    assert i_text < i_nth, "row_index（nth）必须排在 row_text 之后，是最后一档"


def test_no_row_anchor_still_never_invents_one():
    """三档都没有时**不许**凭空按第一行猜 —— 这是原有铁律，加了 row_id 也不能破。"""
    from framework.features.f03_locate.anchor_locate import path_for_table_row

    steps = path_for_table_row(None, "col_58")
    rows = [s for s in steps if s.get("axis") == "row"]
    assert rows == [], f"三档都没有时不许生成行步，实际: {rows}"


# ---------------------------------------------------------------- 3) 执行层
def test_executor_supports_row_id():
    body = _func_src(SCOPE, "step_expr")
    assert 'by == "id"' in body, "`step_expr` 不支持 by=id -> 生成出来的行标识执行不了"


def test_executor_row_id_does_not_hardcode_attr_name():
    body = _func_src(SCOPE, "step_expr")
    # 只看真代码行：注释里提到 `data-rowid=`（解释"不写死它"）是合法的
    code = "\n".join(
        ln.split("#", 1)[0] for ln in body.splitlines()
        if not ln.strip().startswith("#"))
    i = code.find('by == "id"')
    assert i != -1, "找不到 by=id 分支"
    seg = code[i:i + 1200]
    assert "data-rowid=" not in seg, (
        "行标识执行层写死了 `data-rowid=` —— 另一家框架叫 data-rid 就又瞎了")
    assert "starts-with(name(), 'data-')" in seg, (
        "行标识也要用「任意 data-* 属性值」匹配（属性名不写死）")


# ---------------------------------------------------------------- 4) 探测层接线
def test_probe_passes_row_attr_into_table_context():
    body = _func_src(PROBE, "_table_context")
    assert "row_attr" in body, "`_table_context` 没接 row_attr 参数 —— 行标识永远为空"


def test_probe_page_inferrs_attrs_once_not_per_element():
    """推断必须**整页一次**，不能放在逐元素循环里（否则性能崩）。"""
    body = _func_src(PROBE, "probe_page")
    assert "infer_grid_attrs(page)" in body, (
        "`probe_page` 没有做行/列属性推断 —— 生产系统的 data-colid/data-rowid 拿不到")
    # 推断必须在 `for i in range(n)` 循环**之前**
    i_infer = body.find("infer_grid_attrs(page)")
    i_loop = body.find("for i in range(n):")
    assert i_infer != -1 and i_loop != -1
    assert i_infer < i_loop, "推断必须排在逐元素循环之前（否则每个元素都扫一遍全页）"


def test_table_context_does_not_hardcode_data_field():
    body = _func_src(PROBE, "_table_context")
    assert "getAttribute('data-field')" not in body, (
        "`_table_context` 里仍写死 `getAttribute('data-field')` —— 该用传入的 colAttr")


def test_evaluate_never_gets_two_positional_args():
    """Playwright `locator.evaluate(js, arg)` **只接受一个 arg**。

    多传一个会被当成多余位置参数抛错，而调用侧 `except` 一吞 -> 行内上下文整个变 None，
    表现为「明明有 row_id 却不走行内定位」（本次就踩了，排查花了很久）。
    """
    src = _src(PROBE)
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if not (isinstance(f, ast.Attribute) and f.attr == "evaluate"):
            continue
        # locator.evaluate 的合法上限：js + 1 个 arg = 2 个位置参数
        assert len(n.args) <= 2, (
            f"probe.py:{n.lineno} 的 evaluate 传了 {len(n.args)} 个位置参数 —— "
            f"Playwright 只接受 js + 一个 arg，多传会被吞成静默失败")
