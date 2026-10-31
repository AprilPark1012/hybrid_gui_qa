"""V8.7.24 判据：`expect_first_row` 的 `cell_field` 必须用**该步骤所在页**的列。

由来（2026-10-29 用户第二次真机实测，V8.7.23 之后）：
  V8.7.23 的系统提示**生效了** —— AI 终于改用 `expect_first_row`（不再用 `expect_text` 断言
  自己 fill 的值）。但实跑 735s 后 FAILED：

      AssertionError: 表格没有第一行、或没有 'orderName' 列 —— 无法验证「第一条记录」

  真因：AI 写了 `cell_field=orderName`，而那是**订单列表页**的列。
  它要断的**发票列表页根本没有这一列** —— demo 实测 `invoice_list.html` 的 data-field 只有：
      invoiceNo / invoiceType / invoiceDate / businessUnit / contractNo /
      fromOrder / customer / currency / salesman / lineCount
  `orderName` 只在 `orders.html` 里。

  三层都缺：
    ① 提示词把 `row_fields`（**跨页累积的扁平列表**）直接 `json.dumps` 给模型
       -> 它看到一大堆 field，**分不清哪个属于哪一页** -> 跨页串用；
    ② `_warn_nonexistent_row_columns` 拿**跨页全集**判存在性
       -> `orderName` 在订单页里有 -> **静默通过**，一声不响；
    ③ 运行时 `_assert_first_row` 的 `_sel` 是
       `tbody tr:first-child td[data-field='<field>']` -> 找不到该列 -> 报错并 FAILED。

守六件事：
  ① **跨页串用必须报警**（真实场景：`orderName` 断发票列表页）；
  ② **本页正确的列不许误报**（同一个 `orderName` 断订单列表页要放行）；
  ③ 警告里必须**列出该页可用列**（否则 AI 知道错了也不知换哪个）；
  ④ **不传 `pages` 时退回老行为**（全局集合，不误伤 —— 「宁漏不误伤」是项目固定取舍）；
  ⑤ 切页失败要**留痕**（不许静默吞异常后假装没问题）；
  ⑥ 静态检查：提示词里**按页分组渲染**，且带「各页列互不通用」这条规则。
"""
from __future__ import annotations

from pathlib import Path

from framework.features.f02_semantic.explorer_explore import _warn_nonexistent_row_columns
from framework.features.f03_locate.element_map import TestStep

REPO = Path(__file__).resolve().parents[2]

# 真实列清单（照 demo/invoice_list.html 与 demo/orders.html 的 data-field 写的）
_ROW_FIELDS = [
    {"field": "orderName", "header": "订单名称", "index": 4, "kind": "text", "page": "订单列表页"},
    {"field": "orderNo", "header": "订单编号", "index": 3, "kind": "text", "page": "订单列表页"},
    {"field": "invoiceNo", "header": "发票号", "index": 1, "kind": "text", "page": "发票列表页"},
    {"field": "fromOrder", "header": "来源订单", "index": 7, "kind": "text", "page": "发票列表页"},
    {"field": "customer", "header": "客户", "index": 8, "kind": "text", "page": "发票列表页"},
]
_PAGES = [
    {"name": "订单列表页", "url": "http://localhost:8000/orders.html"},
    {"name": "发票列表页", "url": "http://localhost:8000/invoice_list.html"},
]


def _steps(cell_field_on_invoice: str) -> list:
    return [
        TestStep(0, "goto", value="http://localhost:8000/orders.html", desc="打开订单列表页"),
        TestStep(1, "expect_first_row", cell_field="orderName",
                 value="全链路-20261029", desc="订单列表页首行（本页正确）"),
        TestStep(2, "goto", value="http://localhost:8000/invoice_list.html", desc="打开发票列表页"),
        TestStep(3, "expect_first_row", cell_field=cell_field_on_invoice,
                 value="全链路-20261029", desc="发票列表页首行"),
    ]


# ---------------- ① 跨页串用必须报警 ----------------

def test_cross_page_column_is_flagged() -> None:
    """① 拿订单页的 `orderName` 断发票列表页 -> 必须报警（这正是 735s FAILED 的那一步）。"""
    notes = _warn_nonexistent_row_columns(_steps("orderName"), _ROW_FIELDS, pages=_PAGES)
    assert len(notes) == 1, f"跨页串用没被抓到（或误报）：{notes}"
    msg = notes[0]
    assert "orderName" in msg, msg
    assert "发票列表页" in msg, f"没说清是哪一页的问题：{msg}"
    assert "第 3 步" in msg, f"没指出是哪一步：{msg}"


# ---------------- ② 本页正确的列不许误报 ----------------

def test_correct_column_on_own_page_is_quiet() -> None:
    """② 同一个 `orderName` 用在订单列表页（它自己的页）-> 必须放行，不许误报。"""
    notes = _warn_nonexistent_row_columns(_steps("invoiceNo"), _ROW_FIELDS, pages=_PAGES)
    assert notes == [], f"本页正确的列被误报了：{notes}"


# ---------------- ③ 警告要列出该页可用列 ----------------

def test_warning_lists_page_available_columns() -> None:
    """③ 警告里必须给出该页可用列 —— 否则 AI 知道错了也不知换成哪个。"""
    notes = _warn_nonexistent_row_columns(_steps("orderName"), _ROW_FIELDS, pages=_PAGES)
    msg = notes[0]
    for avail in ("invoiceNo", "fromOrder", "customer"):
        assert avail in msg, f"没列出该页可用列「{avail}」：{msg}"
    # 也不许把**别的页**的列当成「该页可用列」列出来
    assert "orderNo" not in msg.split("该页可用列")[-1], (
        f"把订单页的列当成发票页可用列了：{msg}"
    )


# ---------------- ④ 不传 pages -> 老行为，宁漏不误伤 ----------------

def test_without_pages_falls_back_to_global_set() -> None:
    """④ 不传 `pages` 时退回全局集合判存在性（老行为）—— 跨页串用抓不到，但不误伤。"""
    notes = _warn_nonexistent_row_columns(_steps("orderName"), _ROW_FIELDS)
    assert notes == [], (
        "不传 pages 时不该按页判（切不出页就按全局集合，「宁漏不误伤」）"
    )
    # 但「任何页都没有的列」仍要报
    notes2 = _warn_nonexistent_row_columns(_steps("nonexistentCol"), _ROW_FIELDS)
    assert len(notes2) == 1, f"彻底不存在的列也得报：{notes2}"


# ---------------- ⑤ 切页失败要留痕 ----------------

def test_page_split_failure_is_loud(capsys) -> None:
    """⑤ `split_steps_by_page` 抛异常时必须出声，不许静默退化成全局集合。"""
    import framework.features.f02_semantic.explorer_explore as ex

    _orig = ex.split_steps_by_page

    def _boom(*a, **k):
        raise RuntimeError("模拟切页失败")

    ex.split_steps_by_page = _boom
    try:
        _warn_nonexistent_row_columns(_steps("orderName"), _ROW_FIELDS, pages=_PAGES)
    finally:
        ex.split_steps_by_page = _orig
    err = capsys.readouterr().err
    assert "切页失败" in err, f"切页失败被静默吞了（兜底必须留痕）：err={err[:200]!r}"


# ---------------- ⑥ 提示词按页分组 ----------------

def test_prompt_groups_row_fields_by_page() -> None:
    """⑥ 提示词必须**按页分组**渲染列清单，并写明「各页列互不通用」。"""
    src = (REPO / "framework/features/f02_semantic/explorer_explore.py").read_text(encoding="utf-8")
    assert "_by_page.setdefault" in src, (
        "提示词没按 page 分组 -> 模型只看到扁平的一大堆 field，必然跨页串用"
    )
    assert "【{_pn}】的表格列" in src, "没按页打标题"
    assert "各页的列**互不通用**" in src, "没写明各页列互不通用"
    assert "json.dumps(_rf, ensure_ascii=False, indent=1)" not in src, (
        "还在用扁平 json.dumps 渲染列清单 -> 跨页串用会复现"
    )


# ---------------- ⑦ 接线：调用点必须把 pages 传进去 ----------------

def test_wiring_passes_pages_to_warning() -> None:
    """⑦ `_finalize_map` 调 `_warn_nonexistent_row_columns` 时**必须传 `pages`**。

    [!] 这条是补的（第一版 6 条判据漏了这一层）：判据都是**直接调函数并自己传 pages**，
    所以把调用点的 `pages=pages` 断掉时**一条都不红** —— 反向验证当场没变红就是这个原因。
    真正跑真链路时走的才是调用点，断了就等于整个功能失效。
    """
    src = (REPO / "framework/features/f02_semantic/explorer_explore.py").read_text(encoding="utf-8")
    assert "_warn_nonexistent_row_columns(steps, _ALL_ROW_FIELDS or None, pages=pages)" in src, (
        "调用点没把 pages 传进去 -> 按页校验整条链路没接上（判据自己传 pages 测不出来）"
    )


# ==========================================================================
# V8.7.25（2026-10-30 第三次真机实测）：**补正器**也必须按页
#
# 真实现场：第 59 步 `expect_first_row` 在**发票列表页**，AI 写了
#   `cell_field='订单名称'`（表头文案，发票页确实有个同名的**搜索框 label**）
#   -> `_fix_first_row_column_by_header` 拿**跨页全集**的 header->field 映射反查
#   -> 查到**订单列表页**的 `orderName`（同表头、唯一解）-> 把 cell_field 改成 orderName
#   -> 发票页没有这一列 -> 实跑 715s FAILED「表格没有第一行、或没有 'orderName' 列」
#
# 教训：V8.7.24 只把 `_warn_nonexistent_row_columns` 改成按页，
#   **紧挨着它的补正器没改** -> 同一个 bug 换了个门进来。
#   所以「切页」这件事必须收敛成唯一入口 `_steps_page_index`。
# ==========================================================================

_RF = [
    {"field": "orderName", "header": "订单名称", "index": 4, "kind": "text", "page": "订单列表页"},
    {"field": "orderNo", "header": "订单编号", "index": 3, "kind": "text", "page": "订单列表页"},
    {"field": "contractNo", "header": "合同编号", "index": 2, "kind": "text", "page": "发票列表页"},
    {"field": "fromOrder", "header": "来源订单", "index": 7, "kind": "text", "page": "发票列表页"},
    {"field": "invoiceNo", "header": "发票号", "index": 1, "kind": "text", "page": "发票列表页"},
]
_PG = [
    {"name": "订单列表页", "url": "http://localhost:8000/orders.html"},
    {"name": "发票列表页", "url": "http://localhost:8000/invoice_list.html"},
]


def _two_pages_with_header_text() -> list:
    """两个页都用「订单名称」这个表头文案 —— 订单页有这列，发票页没有。"""
    return [
        TestStep(0, "goto", value="http://localhost:8000/orders.html", desc="订单列表页"),
        TestStep(21, "expect_first_row", cell_field="订单名称", value="全链路-x", desc="订单页首行"),
        TestStep(22, "goto", value="http://localhost:8000/invoice_list.html", desc="发票列表页"),
        TestStep(59, "expect_first_row", cell_field="订单名称", value="全链路-x", desc="发票页首行"),
    ]


def test_header_fix_is_page_scoped() -> None:
    """⑧ 补正器只认**该步骤所在页**的 header->field 映射。

    订单列表页有「订单名称」列 -> 补成 `orderName`（正确）；
    发票列表页没有这一列（只有个同名搜索框）-> **不许补**。
    """
    from framework.features.f02_semantic.explorer_explore import _fix_first_row_column_by_header

    steps = _two_pages_with_header_text()
    notes = _fix_first_row_column_by_header(steps, _RF, pages=_PG)

    assert steps[1].cell_field == "orderName", (
        f"订单列表页的「订单名称」该补成 orderName，实际 {steps[1].cell_field!r}"
    )
    assert steps[3].cell_field == "订单名称", (
        f"发票列表页没有「订单名称」这一列，不许补！实际被改成了 {steps[3].cell_field!r}"
        f" —— 这正是不补就要复现的那个 bug"
    )
    assert len(notes) == 1, f"只该报 1 条补正（订单页那条），实际 {len(notes)} 条：{notes}"
    assert "订单列表页" in notes[0], f"补正说明要标出是哪一页：{notes[0]}"


def test_header_fix_without_pages_keeps_old_behavior() -> None:
    """⑨ 不传 `pages` 时退回全局集合（老行为 -> 会串页，但**不误伤**）。

    这条固化的是**降级路径**，不是推荐用法：切不出页时宁可老行为，也不乱补。
    """
    from framework.features.f02_semantic.explorer_explore import _fix_first_row_column_by_header

    steps = _two_pages_with_header_text()
    _fix_first_row_column_by_header(steps, _RF)      # 不传 pages
    assert steps[1].cell_field == "orderName"
    assert steps[3].cell_field == "orderName", "不传 pages 时应退回全局全集（老行为）"


def test_page_index_is_single_entry() -> None:
    """⑩ 切页必须只有一份实现：`_steps_page_index`。

    V8.7.24 的教训就是「改了一个、漏了紧挨着的另一个」。
    这条扫源码：不许再有人自己写 `split_steps_by_page(...)` 拼 `{id(step): 页名}`。
    """
    import ast

    path = (Path(__file__).resolve().parents[2]
            / "framework/features/f02_semantic/explorer_explore.py")
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # 用 AST 找**真实调用**，不扫文本 —— 扫文本会命中 docstring /
    # 注释里的说明（第一版就是被「修复：按 split_steps_by_page() 切页…」这句说明坑红）
    offenders: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if func.name == "_steps_page_index":
            continue                      # 唯一允许的那一处
        for node in ast.walk(func):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", getattr(node.func, "attr", "")) == "split_steps_by_page"):
                offenders.append(f"{func.name}:{node.lineno}")
    assert not offenders, (
        f"`_steps_page_index` 之外还有函数自己切页：{offenders}"
        f" —— 切页逻辑必须唯一，否则 bug 会从另一处复现"
    )


def test_warning_lists_page_columns_for_header_text_typo() -> None:
    """11) 表头文案写错页时，警告必须列出**该页**可用列（AI 才能照着改）。"""
    from framework.features.f02_semantic.explorer_explore import _warn_nonexistent_row_columns

    steps = _two_pages_with_header_text()
    # 先按页补正（发票页那条不补），再警告
    from framework.features.f02_semantic.explorer_explore import _fix_first_row_column_by_header
    _fix_first_row_column_by_header(steps, _RF, pages=_PG)
    notes = _warn_nonexistent_row_columns(steps, _RF, pages=_PG)

    assert len(notes) == 1, f"发票页那条该被警告，实际 {notes}"
    msg = notes[0]
    assert "发票列表页" in msg and "订单名称" in msg, msg
    for avail in ("contractNo", "fromOrder", "invoiceNo"):
        assert avail in msg, f"没列出该页可用列「{avail}」：{msg}"


def test_wiring_passes_pages_to_header_fix() -> None:
    """12) `_finalize_map` 调**补正器**时也必须传 `pages`（接线判据）。

    [!] 这条是补的：上面 ⑧⑨ 两条都是**直接调函数并自己传 pages**，
    把调用点的 `pages=pages` 断掉时**一条都不红**（反向验证当场没变红就是这个原因）。
    真链路走的才是调用点 —— 断了等于补正器仍按跨页全集反查，bug 原样复现。
    这和 V8.7.24 那次「判据全自己传参、接线没人守」是**同一个错误犯了第二次**。
    """
    src = (Path(__file__).resolve().parents[2]
           / "framework/features/f02_semantic/explorer_explore.py").read_text(encoding="utf-8")
    assert "_fix_first_row_column_by_header(steps, _ALL_ROW_FIELDS or None," in src, (
        "补正调用点签名变了"
    )
    assert "pages=pages" in src.split("_fix_first_row_column_by_header(steps, _ALL_ROW_FIELDS or None,")[1][:200], (
        "补正调用点没把 pages 传进去 -> 按页反查整条链路没接上"
    )


def test_both_gates_share_one_page_index() -> None:
    """13) 补正器与警告器必须**都**走 `_steps_page_index`（不许一方漏）。"""
    src = (Path(__file__).resolve().parents[2]
           / "framework/features/f02_semantic/explorer_explore.py").read_text(encoding="utf-8")
    for fn in ("_fix_first_row_column_by_header", "_warn_nonexistent_row_columns"):
        body = src.split(f"def {fn}")[1].split("\ndef ")[0]
        assert "_steps_page_index(" in body, (
            f"{fn} 没有走唯一入口 `_steps_page_index` —— 两处各写一份正是 bug 换门重来的根源"
        )
