# -*- coding: utf-8 -*-
"""特性2 · AI 必须能表达「行内勾选框」（V8.4.3 · Windows 实测暴露）。

事故（AprilPark1012 2026-10-09 在 Windows 上跑 `explore --ai`，删掉 cases/scripts/output 后）：
    `all --workers 2` 与 `run --debug` 都通过，但 AI 链路三轮全挂 —— **每轮错法不同**：

      轮 1  `check` 步骤 **element 留空** -> 映射质量闸拦下（「有 1 个操作步骤没有绑定元素」）
      轮 2  URL 断言失败：AssertionError: Page URL expected to be re.compile('orders\\.html')
      轮 3  Locator.check: Error: **Not a checkbox or radio button**
            Call log: waiting for get_by_role("link", name="HT-1001")
                       locator resolved to <a href="/contract_detail.html?no=HT-1001">HT-1001</a>

真因：**AI 的产出 schema 里根本没有表达「行内那一列的勾选框」的字段**。
    `_StepModel` 只有 `row_text` / `cell_field`，而 `cell_field` 按提示词要求
    「**只能**取探针给的【行内列清单】里的 field」—— 订单列表的**勾选列不是 data-field 列**
    （它是 `<input type=checkbox>`，没有 data-field），于是 AI 无处可写：
    要么留空 element，要么退而求其次把行里的 `HT-1001` 链接当成 checkbox。

而框架**本来就支持**三种列指定方式（`generator._row_col_step` 的白名单）：
    · `cell_field=<data-field>`        —— 有 data-field 的列
    · `cell_by=header` + `cell_field=<表头文案>`
    · `cell_by=index`  + `cell_index=<第 N 列，从 1 起>`  ← **勾选列走这条**

对照证据：能跑通的手搓用例（`cases/orders_invoice_full_lifecycle/ai_..._140528.json`）里
「选中该订单行」正是这么写的：`{"op":"check","row_text":"全链路-{datetime}",
"cell_by":"index","cell_index":1}`。

口径：把框架**已有**的表达能力**如实暴露给 AI**（schema + 提示词），
不许让 AI 因为「schema 里没这个字段」而退化成猜 —— 那属于框架能力没交底，不是 AI 不行。
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.tools.explore import explorer  # noqa: E402

SRC = Path(explorer.__file__).read_text(encoding="utf-8")


def _model_fields(cls_name: str) -> set[str]:
    """取某个 pydantic 模型的字段名（用 AST 读源码，不实例化）。"""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            names = set()
            for st in node.body:
                if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                    names.add(st.target.id)
            return names
    raise AssertionError(f"explorer.py 里找不到模型 {cls_name}")


# ---------------------------------------------------------------- schema 要交底

def test_step_model_exposes_cell_by_and_cell_index():
    """`cell_by` / `cell_index` 必须出现在 AI 的产出 schema 里。

    没有它们 => AI 表达不了「勾选列」（非 data-field 的列）=> 只能留空或抓错控件。
    """
    fields = _model_fields("_StepModel")
    assert "cell_by" in fields, (
        "AI 的 schema 里没有 cell_by => 它无法表达「按表头/按列序号」定位的行内控件"
        "（实测：check 勾选框只能留空 element 或抓成 HT-1001 链接）"
    )
    assert "cell_index" in fields, "AI 的 schema 里没有 cell_index => cell_by=index 用不了"


def test_plan_model_keeps_row_text_and_cell_field():
    """**反向自证**：原有字段不许被删（有 data-field 的列仍走 cell_field 这条路）。"""
    fields = _model_fields("_StepModel")
    assert "row_text" in fields
    assert "cell_field" in fields


# ---------------------------------------------------------------- 提示词要教

def _prompt_src() -> str:
    i = SRC.index("def _build_planner_prompt")
    return SRC[i: i + 40000]


def test_prompt_teaches_cell_by_index_for_checkbox():
    """提示词必须明确教「行内勾选框」怎么写（否则 AI 不知道还有这条路）。"""
    body = _prompt_src()
    assert "cell_by" in body, "提示词没提 cell_by => AI 只会用 cell_field"
    assert "cell_index" in body, "提示词没提 cell_index"
    # 要有「勾选/选择列没有 data-field 时用 index」这类可操作的说明
    assert ("勾选" in body or "check" in body.lower()), "提示词没有把「勾选列」这个场景讲清楚"


def test_prompt_no_longer_forbids_row_locator_for_check():
    """**反向自证**：提示词不许再笼统地说「不要用 row_text/cell_field 去点选择按钮」。

    那句话是针对**弹层里的「选择」按钮**（那种确实有语义名），但措辞会被泛化理解，
    让 AI 连「主列表的勾选框」也不敢用行内定位。
    """
    body = _prompt_src()
    bad = body.count("不要**用 row_text/cell_field 去点")
    if bad:
        # 若保留这句，必须同时限定适用范围（弹层/弹窗）与给出替代（勾选框走 index）
        assert "弹层" in body or "弹窗" in body
        assert "cell_by" in body, "保留了那句禁止，却没给出勾选框的正确写法 => 等于堵死了路"


def test_prompt_mentions_check_action_semantics():
    """`check` 这个 action 要有可操作说明（AI 之前写成了裸 check）。"""
    body = _prompt_src()
    assert "check" in body


# ---------------------------------------------------------------- 链路必须通

def test_teststep_carries_cell_by_through_dict_roundtrip():
    """**链路判据**：`cell_by`/`cell_index` 必须能从 TestStep 序列化出去（落进 cases json）。

    [!] 实测踩过：schema 加了字段、提示词也教了，但 `explorer.py` 构造 TestStep 时没带
        -> AI 写了也在这一步**静默丢掉**（生成器那份读 cell_by 的代码永远拿不到值）。
        只加 schema 不改链路 = 假修。
    """
    from framework.tools.probe.element_map import TestStep

    st = TestStep(order=26, action="check", description="选中该订单行",
                  row_text="全链路-{datetime}", cell_by="index", cell_index=1)
    d = st.to_dict()
    assert d.get("cell_by") == "index", "TestStep.to_dict 丢了 cell_by -> 落盘时 AI 的表达消失"
    assert d.get("cell_index") == 1
    back = TestStep.from_dict(d)
    assert back.cell_by == "index" and back.cell_index == 1, "from_dict 丢了 cell_by/cell_index"


def _code_only(text: str) -> str:
    """剔掉整行注释 —— 判据断言必须只看真代码。

    [!] 这坑踩了三次：`"cell_by" in seg` 会被**我自己写的注释**满足
        （注释里正解释着这个字段），于是摘掉真接线判据照样绿（空转）。
    """
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))


def test_explorer_wiring_passes_cell_by():
    """构造点必须真的把 `cell_by`/`cell_index` 传进 `TestStep`（不许只加 schema 不连线）。"""
    fi = SRC.index("def _plan_to_steps(")
    fj = SRC.find("\ndef ", fi + 1)
    body = (SRC[fi: fj if fj > 0 else len(SRC)]).replace(" ", "")
    assert "steps.append(TestStep(" in body, "结构变了？判据需复核"
    # 取构造点前后一段（含「从 AI 产出取字段」与「框架翻译行内列」两段逻辑）
    seg = body[max(0, body.index("steps.append(TestStep(") - 2600): body.index("steps.append(TestStep(") + 700]
    assert 'getattr(s,"cell_by"' in seg, (
        "构造点没从 AI 产出取 cell_by -> AI 写了也会被丢掉（只加 schema 不改链路 = 假修）"
    )
    assert ("cell_by=cb" in seg) or ('cell_by=getattr(s,"cell_by"' in seg), "最终没把 cell_by 传进 TestStep"
    assert "cell_index" in seg


def test_generator_reads_cell_by_from_step_dict():
    """**反向自证**：生成器那一侧本来就在读（框架早支持），别退化。"""
    gsrc = (ROOT / "framework/tools/generate/generator.py").read_text(encoding="utf-8")
    assert "cell_by" in gsrc and "cell_index" in gsrc, "生成器丢了 cell_by 读取？框架本来就支持它"


def test_output_format_example_lists_row_locator_fields():
    """**最终根因判据**：输出格式示例里必须列出 `row_text`/`cell_field`/`cell_by`/`cell_index`。

    [!] 这是追了四层才见底的那一层：schema 有字段、提示词有教学，
        但「JSON 步骤格式」示例里**没有这几个键**、还写着「严格按此，不要多余字段」
        => AI 只能靠猜（实测它硬塞了 `cell_field="pick"`，那是个不存在的 field 名）。
    """
    i = SRC.index("请把场景规划成")
    seg = SRC[i: i + 2200]   # 行内定位说明紧随格式示例之后
    for key in ("row_text", "cell_field", "cell_by", "cell_index"):
        assert f'"{key}"' in seg, (
            f"输出格式示例里没有 {key} -> AI 受「严格按此」约束不会写它 "
            f"（实测：勾选列只能自造一个假 field 名）"
        )


def test_output_format_forbids_inventing_key_names():
    """格式说明要明确「不许发明键名」——否则 AI 会自造 `pick` 这种名字。"""
    i = SRC.index("请把场景规划成")
    seg = SRC[i: i + 2200]   # 行内定位说明紧随格式示例之后
    assert "不许发明" in seg or "不要发明" in seg or "禁止" in seg, (
        "没写「不许发明字段名」-> AI 自造 `pick` 这类无效键"
    )


# ---------------------------------------------------------------- 确定性兜底

def test_fill_missing_row_column_fills_unique_checkbox():
    """`row_text` 有、列缺失，且表里**只有一个**勾选列 -> 补上（唯一解，不是猜）。"""
    from framework.tools.probe.element_map import TestStep

    steps = [TestStep(order=36, action="check", description="勾选该订单行",
                      row_text="全链路-{datetime}")]
    fields = [{"table": "tbl-orders", "index": 1, "field": "", "header": "", "kind": "checkbox"},
              {"table": "tbl-orders", "index": 2, "field": "orderNo", "header": "订单编号", "kind": ""}]
    notes = explorer._fill_missing_row_column(steps, fields)
    assert steps[0].cell_by == "index" and steps[0].cell_index == 1, (
        "唯一解没补上 -> AI 给的 row_text 步骤仍是「既非合法行内定位、也没 element」"
    )
    assert notes, "补了就要出声（不许静默改产物）"


def test_fill_missing_row_column_refuses_when_ambiguous():
    """**反向自证**：有**多个**勾选列候选 -> **不许**补（诚实降级，交给重试）。"""
    from framework.tools.probe.element_map import TestStep

    steps = [TestStep(order=36, action="check", description="勾选该订单行",
                      row_text="全链路-{datetime}")]
    fields = [{"index": 1, "field": "", "kind": "checkbox"},
              {"index": 5, "field": "", "kind": "checkbox"}]
    explorer._fill_missing_row_column(steps, fields)
    assert steps[0].cell_by is None, "候选不唯一却补了 -> 等于猜，可能勾错列"


def test_fill_missing_row_column_leaves_normal_steps_alone():
    """普通步骤（没有 row_text / 不是勾选语义）**不许动**。"""
    from framework.tools.probe.element_map import TestStep

    steps = [TestStep(order=3, action="click", description="点击搜索", row_text=None),
             TestStep(order=9, action="click", description="点该行订单名称",
                      row_text="全链路-{datetime}", cell_field="orderName")]
    fields = [{"index": 1, "field": "", "kind": "checkbox"}]
    explorer._fill_missing_row_column(steps, fields)
    assert steps[0].cell_by is None and steps[1].cell_by is None, "动了不该动的步骤"


def test_row_field_cache_written_on_cross_page_path():
    """**兜底必须拿得到清单**：跨页路径（本场景实际走的路径）也要写 `_LAST_ROW_FIELDS`。

    [!] 这是兜底「从未触发」的真因：缓存只在**单页**分支写过，而 `explore --ai` 走的是
        **跨页**分支 -> 缓存恒为空 -> `_fill_missing_row_column` 直接返回 -> 全链路白修。
        判据要同时盯住「两处分支都有写」，否则以后加页面又会漏。
    """
    src = SRC.replace(" ", "")
    n_calls = src.count("probe_row_fields(pg)")
    # 同步方式：单页 `clear(); extend(...)` 或跨页 `extend(...)` 都算「同步了缓存」
    n_sync = src.count("_LAST_ROW_FIELDS.clear()") + src.count("_LAST_ROW_FIELDS.extend(")
    assert n_calls >= 2, "probe_row_fields 的调用点少于 2 处（结构变了？判据需复核）"
    assert n_sync >= n_calls, (
        f"probe_row_fields 有 {n_calls} 处调用，但只有 {n_sync} 处同步了兜底缓存 "
        f"-> 未同步的那条路径兜底不生效（实测就是这么漏的：跨页分支没写，兜底恒不触发）"
    )
    # 跨页分支**不许**在循环里 clear：否则跑完只剩最后一页的列（实测勾选列候选因此丢失）
    i = src.index("_LAST_ROW_FIELDS.extend(_page_rf)")
    seg = src[i - 200: i]
    assert "_LAST_ROW_FIELDS.clear()" not in seg.replace(" ", ""), (
        "跨页循环内在 extend 之前 clear -> 每页都把前面的列冲掉，循环结束只剩最后一页 "
        "-> 勾选列候选丢失，兜底不触发（实测两次白跑）"
    )
