# -*- coding: utf-8 -*-
"""行内列标识**不许写死属性名**（V8.8.0 P0-A）。

背景
----
真实生产系统的行内列标识来自前端框架，命名五花八门：

    demo:        <td data-field="orderName">          （字段名即语义）
    生产系统:     <td data-colid="col_57">              （框架生成的列契约，值稳定）
    第三方框架:   <div data-colx="col_57">              （换个名字 + 不是 table）

V8.7.x 及以前 `probe_row_fields` / `probe_div_grid_fields` 都**只认 `data-field`**，
所以换个系统就探到 0 列 -> AI 拿不到列 -> 行内断言只能猜。

V8.8.0 改成**按值的分布推断**（`infer_grid_attrs`）：
  · 行标识 = 该属性值**每行都不同**（`row_1`/`row_2`/`row_3`）
  · 列标识 = 该属性值**同位置跨行相同**（第 1 列每行都是 `col_57`）

判据口径
--------
1. 探测代码里 `data-field` **只能作为兜底默认值**出现，不许是唯一数据源；
2. `probe_row_fields` / `probe_div_grid_fields` **必须真的调用推断**（接线判据）；
3. 推断函数本身**不许出现具体属性名**（只许出现 `data-` 前缀判断）；
4. 推断逻辑正确性：行 = 每行不同，列 = 同列相同（用纯 Python 复现判据）；
5. 老行为不变：`data-field` 页面仍然走默认路径。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "framework" / "features" / "f03_locate" / "probe.py"


def _src() -> str:
    assert PROBE.is_file(), f"找不到 {PROBE}"
    return PROBE.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_src())


def _func(name: str) -> ast.FunctionDef:
    for n in ast.walk(_tree()):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n
    raise AssertionError(f"模块里找不到函数 {name}")


def _body(name: str) -> str:
    return ast.get_source_segment(_src(), _func(name)) or ""


def _py_code_only(text: str) -> str:
    """去掉 Python 注释与三引号 docstring，只留**真代码行**。

    为什么需要：判据要钉的是「代码里怎么取值」，而注释里写 `data-field` 是在解释历史，
    属于合法内容。早期版本直接扫原文，结果把解释性注释也算成违规 -> **假红**。
    """
    out: list[str] = []
    in_doc = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('"""') or s.startswith("'''"):
            # 单行 docstring 直接跳过；三引号成对切换
            if s.count('"""') >= 2 or s.count("'''") >= 2:
                continue
            in_doc = not in_doc
            continue
        if in_doc:
            continue
        if s.startswith("#"):
            continue
        # 行尾注释也去掉（简单处理：不在引号里的 # 之后）
        if "#" in line:
            line = line.split("#", 1)[0]
        out.append(line)
    return "\n".join(out)


def _html_code_only(text: str) -> str:
    """去掉 HTML 注释块 `<!-- ... -->`，只留真标签。"""
    out: list[str] = []
    in_c = False
    for line in text.splitlines():
        s = line
        while True:
            if in_c:
                j = s.find("-->")
                if j == -1:
                    s = ""
                    break
                s = s[j + 3:]
                in_c = False
            else:
                i = s.find("<!--")
                if i == -1:
                    break
                j = s.find("-->", i)
                if j == -1:
                    s = s[:i]
                    in_c = True
                    break
                s = s[:i] + s[j + 3:]
        if s.strip():
            out.append(s)
    return "\n".join(out)


# ---------------------------------------------------------------- 1) 不写死属性名
def test_probe_row_fields_is_not_hardcoded_to_data_field():
    """主路径必须走推断出的 `col_attr`；`data-field` 只许在**兜底分支**里出现。

    · 主路径 = `get_attribute(col_attr)`
    · 兜底   = `if not field and col_attr != "data-field":` 这类**带条件**的分支
    判据看的是「这一行有没有被条件保护」，所以取**前 3 行上下文**一起看 ——
    只扫单行会把合法的兜底行误判成写死（假红）。
    """
    body = _py_code_only(_body("probe_row_fields"))
    assert "get_attribute(col_attr)" in body, (
        "`probe_row_fields` 主路径没有用 `col_attr` 取列值 —— "
        "换个框架（data-colid / data-colx）就探不到列")
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if "data-field" not in line:
            continue
        ctx = "\n".join(lines[max(0, i - 3):i + 1])
        assert ("col_attr" in line or "not field" in ctx), (
            f"这一行的 data-field 没有任何条件保护（无条件直接用 = 写死属性名）：\n"
            f"    上下文：\n{ctx}")


def test_probe_row_fields_uses_inferred_attr():
    body = _py_code_only(_body("probe_row_fields"))
    assert "infer_grid_attrs(" in body, (
        "`probe_row_fields` 没有调用 `infer_grid_attrs` —— 接线没做，推断写了也白写")
    assert "col_attr" in body, "`probe_row_fields` 里没有 `col_attr` 变量，说明没用推断结果"


def test_div_grid_attr_is_parameterized():
    """div 网格那条路径同样不许写死 —— JS 必须接受属性名参数。"""
    body = _py_code_only(_body("probe_div_grid_fields"))
    assert "page.evaluate(_DIV_GRID_JS, attr)" in body, (
        "`probe_div_grid_fields` 没有把属性名传给 JS —— div 网格仍写死 data-field")
    src = _src()
    assert "querySelectorAll('[data-field]')" not in src, (
        "`_DIV_GRID_JS` 里还有写死的 `[data-field]` 选择器")


def _infer_js_code() -> str:
    """取推断 JS 的**代码行**（去掉 `//` 注释）。"""
    src = _src()
    js = src.split("_INFER_GRID_ATTRS_JS = r")[1].split('"""')[1]
    out = []
    for line in js.splitlines():
        s = line.split("//", 1)[0] if "//" in line else line
        if s.strip():
            out.append(s)
    return "\n".join(out)


def test_infer_function_has_no_concrete_attr_names():
    """推断逻辑必须**只认 data- 前缀**，不许出现具体属性名（否则就是枚举白名单）。"""
    js = _infer_js_code()
    for banned in ("data-field", "data-colid", "data-colx", "data-rowid", "data-rid"):
        assert banned not in js, (
            f"推断逻辑里出现了具体属性名 `{banned}` —— 那不是「推断」而是「枚举」，"
            f"换一家框架再换名字照样瞎。只许按 `data-` 前缀 + 值的分布判断。")
    assert "indexOf('data-')" in js or "startswith('data-')" in js, (
        "推断逻辑必须有「只认 data- 前缀」的判断")


# ---------------------------------------------------------------- 2) 推断判据本身
def _infer_row_attr(rows_attrs: list[dict[str, str]]) -> str:
    """用 Python 复现 JS 的行标识判据：某属性每行都有值且值互不相同。"""
    if len(rows_attrs) < 2:
        return ""
    cand: dict[str, list[str]] = {}
    for am in rows_attrs:
        for k, v in am.items():
            if v:
                cand.setdefault(k, []).append(v)
    for k, vs in cand.items():
        if len(vs) == len(rows_attrs) and len(set(vs)) == len(rows_attrs):
            return k
    return ""


def _infer_col_attr(row_cells_attrs: list[list[dict[str, str]]]) -> str:
    """用 Python 复现 JS 的列标识判据：同列位置跨行值相同。"""
    if len(row_cells_attrs) < 2:
        return ""
    by_attr: dict[str, dict[int, list[str]]] = {}
    for cells in row_cells_attrs:
        for ci, am in enumerate(cells):
            for k, v in am.items():
                if v:
                    by_attr.setdefault(k, {}).setdefault(ci, []).append(v)
    best, best_n = "", 0
    for k, by_col in by_attr.items():
        stable = all(len(vs) >= 2 and len(set(vs)) == 1 for vs in by_col.values())
        if stable and len(by_col) > best_n:
            best, best_n = k, len(by_col)
    return best


def test_row_attr_rule_each_row_differs():
    rows = [{"data-rowid": "row_1"}, {"data-rowid": "row_2"}, {"data-rowid": "row_3"}]
    assert _infer_row_attr(rows) == "data-rowid"


def test_row_attr_rule_rejects_constant_value():
    """值每行都一样（如 data-role="data"）不能被当行标识。"""
    rows = [{"data-role": "data"}, {"data-role": "data"}, {"data-role": "data"}]
    assert _infer_row_attr(rows) == ""


def test_col_attr_rule_same_column_same_value():
    rows = [
        [{"data-colid": "col_57"}, {"data-colid": "col_58"}],
        [{"data-colid": "col_57"}, {"data-colid": "col_58"}],
    ]
    assert _infer_col_attr(rows) == "data-colid"


def test_col_attr_rule_rejects_per_row_varying():
    """值每行都不同（那是行标识的特征）不能被当列标识。"""
    rows = [
        [{"data-rid": "row_1"}, {"data-rid": "row_1"}],
        [{"data-rid": "row_2"}, {"data-rid": "row_2"}],
    ]
    assert _infer_col_attr(rows) == ""


# ---------------------------------------------------------------- 3) 兜底链仍在
def test_data_field_remains_the_fallback():
    """老页面（data-field）必须继续能探到 —— 兜底默认值不许丢。"""
    body = _body("probe_row_fields") + _body("probe_div_grid_fields")
    assert '"data-field"' in body, (
        "`data-field` 作为**兜底默认值**被彻底删掉了 —— 老页面（demo 全用它）会直接失效")


# ---------------------------------------------------------------- 4) 三类页面各有判据页
def test_demo_pages_exist_for_three_structures():
    """三类结构必须有真页面可测，否则「通用」只是一句话。"""
    demo = ROOT / "demo"
    for name, why in [
        ("prod_style_grid.html", "生产系统形态（tr[data-rowid] + td[data-colid]）"),
        ("header_only_grid.html", "零 data-* 属性（只能靠表头兜底）"),
        ("attr_name_variant.html", "属性名换成 data-rid/data-colx + div 网格（证明没写死）"),
    ]:
        f = demo / name
        assert f.is_file(), f"缺判据页 {name}（{why}）—— 没这个页面就验不出通用性"
        txt = f.read_text(encoding="utf-8")
        assert len(txt) > 800, f"{name} 内容太短，不像真实表格页"


def test_variant_page_really_uses_different_attr_names():
    """核心证据页必须真的用别的属性名 —— 否则它和 demo 页面没区别，验不出东西。"""
    f = ROOT / "demo" / "attr_name_variant.html"
    # 只看**真标签**：说明性注释里提到 `data-field`（解释"为什么不用它"）是合法的
    txt = _html_code_only(f.read_text(encoding="utf-8"))
    assert "data-colx" in txt and "data-rid" in txt, (
        "`attr_name_variant.html` 没有用 data-colx / data-rid —— 它就证明不了「不写死属性名」")
    assert "data-field" not in txt, (
        "`attr_name_variant.html` 的**真标签**里出现了 data-field —— 那这条判据就自相矛盾了")


# ---------------------------------------------------------------- 5) 执行层也不许写死
SCOPE = ROOT / "framework" / "features" / "f03_locate" / "scope_locate.py"


def _scope_step_expr_code() -> str:
    src = SCOPE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == "step_expr":
            return _py_code_only(ast.get_source_segment(src, n) or "")
    raise AssertionError("scope_locate.py 里找不到 step_expr")


def test_executor_does_not_hardcode_data_field():
    """**执行层**拼列选择器时也不许写死 `data-field`。

    探测层改了、执行层没改 = 半修：清单里明明有 `col_57`，跑起来却去
    `td[data-field='col_57']` 里找，永远找不着（生产系统整类用例全废）。
    """
    body = _scope_step_expr_code()
    assert "td[data-field=" not in body, (
        "`step_expr` 里仍在拼 `td[data-field=...]` —— 探测层能拿到列、执行层却定位不到。"
        "必须改成与属性名无关的写法（XPath 按任意 data-* 属性值匹配）。")


def test_executor_uses_attr_agnostic_selector():
    body = _scope_step_expr_code()
    assert "starts-with(name(), 'data-')" in body, (
        "`step_expr` 的列定位没有用 `starts-with(name(),'data-')` 这种属性名无关的写法 —— "
        "那就还是只认某一家框架的命名")


def test_executor_rejects_quote_values_instead_of_building_broken_xpath():
    """XPath 字符串没有转义语法 —— 含引号的值必须**放弃**，不许拼出语法错误表达式。"""
    body = _scope_step_expr_code()
    assert "return None" in body, "含引号的值必须返回 None（让调用方退下一档），不许硬拼"
    # 含引号判断必须在拼 XPath **之前**
    i_guard = body.find("in str(val)")
    i_build = body.find("starts-with(name()")
    assert i_guard != -1 and i_build != -1, "找不到引号判断或 XPath 拼接"
    assert i_guard < i_build, "引号判断必须排在拼 XPath 之前，否则会拼出坏表达式"
