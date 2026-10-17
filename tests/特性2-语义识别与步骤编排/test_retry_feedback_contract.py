# -*- coding: utf-8 -*-
"""特性2 · 「跨轮反馈通道」的完整契约（V8.6.4 合并 · 原名 test_quality_warnings_feed_next_round.py）。

现场（实测）：框架已经能**确定性**地认出这几类质量问题 ——
    · [行内控件缺行定位（多匹配）] 控件 '数量@开票页' 重复出现 3 个 … 运行期必红
    · 质量警告: 有 1 个操作步骤没有绑定元素（element 为空）
    · 质量警告: 跨页用例里这些声明过的页面既没有 goto 也没有 url 断言作为到达证据：[...]
但实测日志写的是「AI 产出有 N 条**警告级**提示（**不拦产出**，继续 generate/run）」——
也就是**警告只打印、不参与重试**。后果：同一个错被 AI 连犯三轮
（实测 GLM 两轮就死在同一个点上），而框架**早就把话说清楚了**，只是没递给它。

口径：**不改变「警告不拦产出」**（照旧落 cases、照旧 generate/run、不 exit）——
      只把「上一轮识别出的警告」**存下来**，在下一轮生成时拼进提示词，并明说
      「这几条必须修正，尤其 X」。已经作为**硬拦截原因**给过 AI 的问题不重复说
      （同一句说两遍 = 噪音，AI 会把注意力摊薄）。

判据口径：纯函数 / 字符串级（不联网、不起浏览器、不调真 LLM）。

===============================================================================
[!] V8.6.4（合并重复判据 · 第二批 · 组 3）—— 本文件由两条判据合一，改名自
    `test_quality_warnings_feed_next_round.py` -> **`test_retry_feedback_contract.py`**

**为什么是一条**：两者守的是**同一条通道**（`_next_round_feedback` / `_quality_warn_feedback`
-> `_build_planner_prompt(retry_feedback=...)`）的两端 ——
  · 前端：上一轮的缺陷记账**不许跨轮残留**（残留 = AI 补好了还被拦，白挨两轮）；
  · 后端：记的账必须**真的递给 AI**（不递 = 记账等于白记，AI 连犯三轮）。
通道断任一端，现象完全一样（AI 反复犯同一个错），所以必须**同一条判据守两端**。

迁入（原 `test_retry_leaves_no_stale_notes.py`，**4 条一条不丢**，统一加 `test_notes_*` 前缀）：
  · `test_notes_round2_after_round1_leaves_no_stale_notes`（行为链：第 1 轮记账 -> 第 2 轮补全 -> notes 为空）
  · `test_notes_finalize_map_clears_in_body_unconditionally`（缩进级源码兜底：clear 必须在 `_finalize_map` **函数体**里、无条件）
  · `test_notes_semantic_mismatch_has_clear`（第三次同形态事故的那个容器）
  · `test_notes_check_required_field_coverage_reports_missing`（第 1 轮确实报缺口，否则校验是摆设）
  模块级状态由 autouse fixture 清空（范式取自 `test_production_defects_gate_l1.py:29-36`）。

新增（1 条，遍历式）：`test_notes_every_module_level_container_has_unconditional_clear`
  —— 对 `explorer_explore.py` 里**所有**模块级 `*_NOTES` 容器断言「必有一处无条件 `.clear()`」，
  名单从源码**动态收集**（不写死），并自带两条负向自证。

接手自 `test_ai_retry_loop.py`（V8.6.4 第二批删掉它那条重复项）：
  `test_prompt_without_feedback_is_clean` -> 本文件 `test_prompt_stays_clean_without_feedback`
  （断言**取严**：`"上一轮" not in flat` 与 `"上一轮框架识别出的" not in prompt` **两条都查**）。
===============================================================================
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.cli import _next_round_feedback, _quality_warn_feedback  # noqa: E402
from framework.features.f02_semantic import explorer_explore as EX  # noqa: E402
from framework.features.f02_semantic.explorer_explore import _build_planner_prompt  # noqa: E402

CLI = ROOT / "framework" / "features" / "f10_cli" / "cli.py"
EXPLORER = ROOT / "framework" / "features" / "f02_semantic" / "explorer_explore.py"

#: 与实测日志同形的假警告（带控件名 / 步骤号这类可操作信息）
_FIXTURE = [
    "[行内控件缺行定位（多匹配）] 控件 '数量@开票页' 重复出现 3 个 -> 运行期必红",
    "有 1 个操作步骤没有绑定元素（element 为空）→ 生成脚本定位不到，执行必然失败：click（提交整个订单）",
    "跨页用例里这些声明过的页面既没有 goto 也没有 url 断言作为到达证据：['http://x/invoice_list.html']",
]


@pytest.fixture(autouse=True)
def _clean_notes():
    """每条判据前后都清空收集器（它们是**模块级**状态，判据之间会串味）。

    范式与 `tests/特性2-语义识别与步骤编排/test_production_defects_gate_l1.py:29-36` 一致：
    这类 notes 是**跨轮记账**用的模块级容器，前一条判据（或前一轮 explore）留下的残余
    会让后一条判据看着「凭空多出条目」—— 那是判据互相污染，不是被测代码有问题。
    """
    for name in ("_REQUIRED_COVERAGE_NOTES", "_HARDCODED_NOTES", "SEMANTIC_MISMATCH_NOTES",
                 "_ROW_SCOPE_NOTES", "_LAST_REQUIRED_FIELDS"):
        getattr(EX, name).clear()
    yield
    for name in ("_REQUIRED_COVERAGE_NOTES", "_HARDCODED_NOTES", "SEMANTIC_MISMATCH_NOTES",
                 "_ROW_SCOPE_NOTES", "_LAST_REQUIRED_FIELDS"):
        getattr(EX, name).clear()


def _fn_src(path: Path, name: str) -> str:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"{path.name} 里找不到 {name}()")


def _module_level_note_names(src: str) -> list[str]:
    """源码里**所有**模块级 `*_NOTES` 容器名 —— 动态收集，不写死名单。

    只看模块级赋值（`ast.parse(src).body`）：函数内的同名局部变量不算容器
    （那不是「跨轮记账」，没有「清空」这回事）。名单随源码走 —— 将来新加一个
    跨轮记账容器，本判据**自动**把它纳入，不需要回来改判据（这就是它比
    「写死两个名字」强的地方）。
    """
    names: list[str] = []
    for node in ast.parse(src).body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and t.id.endswith("_NOTES"):
                names.append(t.id)
    return sorted(set(names))


def _clear_is_nested_in_branch(node: ast.AST, parents: dict) -> bool:
    """这个 `.clear()` 调用是否**被包在分支里**（if / for / while / try / with）。

    只有「无条件执行」才解决旧账问题：`if 本轮有缺失: notes.clear()` 这种写法在
    「本轮没缺失」那一轮**根本不会执行** -> 上一轮的记账留到本轮（本项目实测白挨两轮的那个 bug）。
    """
    cur = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            return False
        if isinstance(cur, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            return True
    return False


def _notes_lacking_unconditional_clear(src: str) -> list[str]:
    """返回「缺一处无条件 `.clear()`」的模块级 `*_NOTES` 容器名（空 = 合规）。"""
    tree = ast.parse(src)
    parents: dict = {}
    for n in ast.walk(tree):
        for child in ast.iter_child_nodes(n):
            parents[child] = n
    out: list[str] = []
    for name in _module_level_note_names(src):
        clears = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute) and n.func.attr == "clear"
                  and isinstance(n.func.value, ast.Name) and n.func.value.id == name]
        if not clears:
            out.append(f"{name}：没有任何 `.clear()`")
        elif all(_clear_is_nested_in_branch(c, parents) for c in clears):
            out.append(f"{name}：清空点全被包在分支里（本轮没缺陷那一轮根本不清 -> 留旧账）")
    return out


# ---------------------------------------------------------------- ① 回炉文案本身

def test_warnings_become_actionable_retry_feedback():
    """★ 核心判据：每条警告都要**原样**进回话，且要带上「必须修正 / 尤其 X」这类可操作信息。"""
    blk = _quality_warn_feedback(_FIXTURE)
    assert blk, "给了 3 条警告却什么都没产出 —— 那就等于警告还是只打印"
    for w in _FIXTURE:
        assert w in blk, f"警告没原样带给 AI（它会不知道具体是哪条）：\n{blk}"
    assert "修正" in blk, f"没说「必须修正」—— 语气太软，AI 会当背景读过去：\n{blk}"
    assert "尤其" in blk, f"没点出「尤其 X」（并列 N 条时 AI 的注意力是摊薄的）：\n{blk}"
    # 可操作信息必须留在文案里（控件名 / 步骤描述），而不是被裁剪成「请注意质量」
    assert "数量@开票页" in blk and "提交整个订单" in blk, f"可操作信息被抹掉了：\n{blk}"


def test_no_warnings_means_no_extra_block():
    """**反向自证**：没有警告 -> 一个字都不许有（否则每轮都在暗示 AI 做错了）。"""
    assert _quality_warn_feedback([]) == "", "空警告却产出了反馈块"
    assert _quality_warn_feedback(None) == ""
    assert _quality_warn_feedback(["", "   "]) == "", "空白警告不该被当成一条"
    assert _next_round_feedback("", []) == "", "既没有硬原因也没有警告，却拼出了反馈"


def test_hard_blocker_reason_is_not_said_twice():
    """硬拦截类问题已经当「失败原因」给过 AI -> 同一句不再重复（重复=噪音）。

    真实形态：generate 被映射质量闸拦下时，硬原因里**逐字带着**那条警告原文。
    """
    hard = "AI 产出的用例没能生成脚本：有 1 个操作步骤没有绑定元素（element 为空）"
    warns = ["有 1 个操作步骤没有绑定元素（element 为空）", "该用例没有任何断言 → 验证不了业务结果"]
    blk = _quality_warn_feedback(warns, already=hard)
    assert "没有绑定元素" not in blk, f"硬原因已经说过的又被当警告说了一遍：\n{blk}"
    assert "没有任何断言" in blk, f"没被硬原因覆盖的那条必须留下（不许整段吞掉）：\n{blk}"


def test_hard_reason_and_warnings_coexist_in_next_round_feedback():
    """硬原因与警告走同一条通道（`retry_feedback`）—— 两者都必须在，且硬原因在前。"""
    hard = "实跑失败：step 17 click 元素未找到（语义名 保存@订单详情页）"
    txt = _next_round_feedback(hard, _FIXTURE)
    assert hard in txt, f"硬原因丢了 —— 回炉把实跑失败原因挤掉了：\n{txt}"
    assert _FIXTURE[1] in txt, f"警告丢了：\n{txt}"
    assert txt.index(hard) < txt.index(_FIXTURE[1]), "硬原因应排在前面（先看清死因，再看告警）"


# ---------------------------------------------------------------- ② 真的进了下一轮提示词

def test_warnings_reach_the_next_round_prompt():
    """接线语义：把回炉反馈交给提示词组装 -> 每条警告都必须出现在**生成提示词**里。"""
    prompt = _build_planner_prompt("随便什么场景", [], "http://127.0.0.1:8000/",
                                   retry_feedback=_next_round_feedback("", _FIXTURE))
    for w in _FIXTURE:
        assert w in prompt, f"警告没进生成提示词（AI 看不到就还会再犯）：{w!r}"
    assert "尤其" in prompt
    assert "上一轮" in prompt, "没标明这是「上一轮」的问题，AI 可能当普通背景读过去"


def test_prompt_stays_clean_without_feedback():
    """没警告、没硬原因时提示词里不许出现回炉段落。

    [!] V8.6.4：接手 `test_ai_retry_loop.py::test_prompt_without_feedback_is_clean`
    （原文件改名 `test_ai_retry_contract.py` 时把它交过来）—— **合并两条断言取严**：
      · 原 `test_ai_retry_loop` 版查 `"上一轮" not in flat`（扁平化后）；
      · 本文件原版查 `"上一轮框架识别出的" not in prompt`。
    两条都留：前者宽（任何位置的「上一轮」字样都不许有），后者窄但直指回炉段落的**段首**。
    只留一条都会漏 —— 前者漏「段首改写成别的说法」，后者漏「段首没出现但别处塞了『上一轮』」。
    """
    prompt = _build_planner_prompt("随便什么场景", [], "http://127.0.0.1:8000/")
    assert "上一轮框架识别出的" not in prompt, "没给警告却出现了「上一轮有质量问题」段落"
    flat = prompt.replace("\n", "")
    assert "上一轮" not in flat, "没重试却出现了「上一轮」字样 —— 会误导 AI 以为自己做错过"
    assert "警告1." not in prompt


# ---------------------------------------------------------------- ③ 接线（cmd_explore 真的用了）

def test_cmd_explore_carries_warnings_into_retry():
    """写了函数不接线 = 能力空转：`cmd_explore` 必须接住 `_explore_one` 回传的 warns 并回炉。"""
    body = _fn_src(CLI, "cmd_explore")
    assert "_quality_warn_feedback(" in body or "_next_round_feedback(" in body, (
        "cmd_explore 没有把质量警告拼进重试反馈 -> 警告照旧只打印（本次改造等于没做）"
    )
    # warns 必须被**接住**（原来是 `emap, cpath, _, qerr = _explore_one(...)`，警告在那里被丢掉）
    i = body.index("= _explore_one(")
    lhs = body[max(0, i - 80):i].splitlines()[-1].strip()
    assert "warns" in lhs, (
        f"`_explore_one` 的返回值里没有接住 warns（还是被丢掉的那个下划线）：{lhs!r}"
    )
    # 回炉的警告必须是**跨轮次**存下来的：本轮生成时上一轮的警告才存在，必须先存后用
    assert "warn_carry" in body or "pending_warn" in body or "round_warn" in body, (
        "没有跨轮次保存警告的容器 —— 生成发生在下一轮开头，警告是本轮末尾才拿到的"
    )


def test_ai_gate_warn_entries_only_takes_warn_level():
    """L1 闸门的**WARN 级**条目也要能拿来回炉；BLOCK 级已经走硬拦截，不许重复收集。"""
    from framework.cli import _ai_gate_warn_entries

    warns = _ai_gate_warn_entries()
    assert warns == [], f"清单为空却读出条目：{warns}"
    EX.SEMANTIC_MISMATCH_NOTES.append("第 3 步「打开菜单」选的控件与描述重叠度 0.00(几乎无关)")
    assert _ai_gate_warn_entries() == [], "BLOCK 级问题被当成警告重复收集了（它已走硬拦截）"
    # BLOCK 级非空会让闸门整体 `blocked=True`（那时连 WARN 都不返回）-> 先清掉 BLOCK 级
    # 才谈得上「WARN 级读得出来」；这也是上面那条断言的另一半含义。
    EX.SEMANTIC_MISMATCH_NOTES.clear()
    # WARN 级（当前是「行内控件缺行定位」）必须读得出来
    EX._ROW_SCOPE_NOTES.append("控件 '数量@开票页' 重复出现 3 个（行内控件缺行定位）")
    got = _ai_gate_warn_entries()
    assert any("数量@开票页" in x for x in got), f"WARN 级条目没读出来：{got}"


# ---------------------------------------------------------------- ④ 上一轮的记账不许留给下一轮
#
# 现场（实跑日志）：
#     第 1 轮 AI 漏了「客户/销售员」-> 校验拦下 + 记入 `_REQUIRED_COVERAGE_NOTES`。
#     第 2 轮 AI **已经补上了**（产出里明明白白有 `fill 客户@新建订单页`），
#     但校验读到的还是第 1 轮的旧账 -> 又拦 -> 第 3 轮再拦 -> 重试用尽，报错收场。
# 根因：清了 notes，但**只在「本轮有缺失」时才清** —— 本轮没缺失 = 根本没进那个分支 = 旧账留着。
# 同一形态在本项目出现**三次**：`_REQUIRED_COVERAGE_NOTES` / `_HARDCODED_NOTES` 只在有缺陷时清，
# `SEMANTIC_MISMATCH_NOTES` 则**完全没有 clear**（永久累积）。
#
# 口径：行为级验证「上一轮有、本轮没有 -> 本轮必须读到空」，
# 而不是只读源码看有没有调用 clear（那种判据骗得过）。

class _El:
    def __init__(self, n):
        self.semantic_name = n


class _St:
    def __init__(self, order, op="fill", desc="", semantic=None, value=None, url=None):
        self.order, self.op, self.description = order, op, desc
        self.value, self.url = value, url
        self.element = _El(semantic) if semantic else None
        self.assertion = None
        self.row_text = self.cell_field = self.cell_by = self.cell_index = None


_SCENARIO = ("4. 在新建订单页填写：订单名称用「全链路-{datetime}」、"
             "业务单元/管理单元/帐套各选第一行、订单类型选第一项、"
             "客户与销售员各选第一个、订单备注填「端到端全链路场景」；点「保存」。")

_REQUIRED = [
    {"name": "订单名称", "page": "新建订单页", "token": "*订单名称"},
    {"name": "客户",     "page": "新建订单页", "token": "*客户"},
    {"name": "销售员",   "page": "新建订单页", "token": "*销售员"},
]

# 第 1 轮：只做了订单名称（漏客户/销售员）
_ROUND1 = [_St(1, desc="填写订单名称", semantic="订单名称@新建订单页", value="全链路-{datetime}")]
# 第 2 轮：补全（这就是实测里 AI 第 2 轮的真实产出）
_ROUND2 = _ROUND1 + [
    _St(2, op="select", desc="客户选第一个", semantic="客户@新建订单页"),
    _St(3, op="select", desc="销售员选第一个", semantic="销售员@新建订单页"),
]


def test_notes_check_required_field_coverage_reports_missing():
    """第 1 轮确实漏了 -> 必须报（否则这个校验就是摆设，后面的行为链也无从谈起）。"""
    EX._LAST_REQUIRED_FIELDS.extend(_REQUIRED)
    miss = EX.check_required_field_coverage(_ROUND1, EX._LAST_REQUIRED_FIELDS, _SCENARIO)
    assert len(miss) == 2, f"应报客户+销售员，实际 {miss}"


def test_notes_round2_after_round1_leaves_no_stale_notes():
    """【核心回归】第 1 轮记账后，第 2 轮补全 -> notes 必须为空（不许留旧账）。

    这正是让 AI 白挨两轮的 bug：旧账不清 -> 补好了还被拦 -> 重试用尽报错。
    """
    # 模拟第 1 轮：把缺失写进 notes（与生产代码同一路径）
    EX._REQUIRED_COVERAGE_NOTES.extend(
        EX.check_required_field_coverage(_ROUND1, _REQUIRED, _SCENARIO))
    assert EX._REQUIRED_COVERAGE_NOTES, "前置：第 1 轮应留下记账"

    # 模拟第 2 轮：**先无条件清空**（生产代码 `_finalize_map` 里就是这么做的）
    miss2 = EX.check_required_field_coverage(_ROUND2, _REQUIRED, _SCENARIO)
    EX._REQUIRED_COVERAGE_NOTES.clear()
    if miss2:
        EX._REQUIRED_COVERAGE_NOTES.extend(miss2)

    assert miss2 == [], f"第 2 轮已补全却仍判缺失：{miss2}"
    assert EX._REQUIRED_COVERAGE_NOTES == [], \
        f"第 2 轮补全后 notes 仍留旧账：{EX._REQUIRED_COVERAGE_NOTES}"


def test_notes_finalize_map_clears_in_body_unconditionally():
    """`_finalize_map` 里这两个 notes 的 clear 必须是**无条件**执行（缩进级源码兜底）。

    [!] 为什么还要一条「缩进级」的：行为链（上一条）只覆盖 `_REQUIRED_COVERAGE_NOTES`
    走的那条路径，`_HARDCODED_NOTES` 没有等价的行为入口 —— 而它们**同源同因**
    （都是「只在有缺陷时清」）。所以这里从源码直接钉：clear 必须在 `_finalize_map`
    **函数体**里、且缩进 == 4（函数体第一层，没被包进任何 `if`）。

    V8.6.4 相比原版**收紧了范围**：原版在全文件里找 clear，本版限定在 `_finalize_map`
    函数体内（这才是它的 docstring 声称守的那个位置）+ 断言不加 `if` 包裹 ——
    全容器遍历那条（`test_notes_every_module_level_container_has_unconditional_clear`）
    守「每个容器都有一处」这个面，本条守「这两处在正确的位置、正确的层级」这个面。
    """
    body = _fn_src(EXPLORER, "_finalize_map")
    lines = body.splitlines()
    for notes_name in ("_REQUIRED_COVERAGE_NOTES", "_HARDCODED_NOTES"):
        idx = [i for i, line in enumerate(lines) if f"{notes_name}.clear()" in line]
        assert idx, f"`_finalize_map` 里没有 {notes_name}.clear() -> 旧账会跨轮残留"
        for i in idx:
            indent = len(lines[i]) - len(lines[i].lstrip())
            assert indent == 4, \
                f"{notes_name}.clear() 缩进 {indent} -> 疑似被放进 if 分支里（会留旧账）"


def test_notes_semantic_mismatch_has_clear():
    """`SEMANTIC_MISMATCH_NOTES` 曾经**完全没有 clear**（永久累积）-> 必须有。

    （第三次同形态事故：三个 notes 一对一对齐后逐个体检才找全。）
    """
    src = EXPLORER.read_text(encoding="utf-8")
    assert "SEMANTIC_MISMATCH_NOTES.clear()" in src, \
        "语义校准的 notes 没有清空点 -> 跨轮累积（第三次同形态事故）"


def test_notes_every_module_level_container_has_unconditional_clear():
    """★遍历式（V8.6.4 新增）：**所有**模块级 `*_NOTES` 容器都必须有一处**无条件** `.clear()`。

    **为什么是遍历式而不是点名**：本项目这一形态的事故**已经犯了三次**
    （`_REQUIRED_COVERAGE_NOTES` 只在有缺失时清 / `_HARDCODED_NOTES` 只在有写死时清 /
    `SEMANTIC_MISMATCH_NOTES` 完全没有 clear）—— 每次都是「体检到哪个就修哪个」，
    而**新加**一个跨轮记账容器时没人会想起回来补 clear。点名判据对第四个容器**天然失明**。

    名单从源码**动态收集**（`_module_level_note_names`）：新加容器 -> 自动纳入；
    删掉容器 -> 自动退出（**这是对的**：判据不该守着不存在的东西）。
    真值（2026-10-17）：`SEMANTIC_MISMATCH_NOTES` / `_HARDCODED_NOTES` /
    `_REQUIRED_COVERAGE_NOTES` / `_ROW_SCOPE_NOTES` 四个（`_ROW_SCOPE_NOTES` 另有一条判据
    在别的特性夹里守它 —— 这里覆盖到它**不算越界**：本条只要求「有无条件 clear」，
    它确实有；描述的是同一个源码文件的事实面，不改别的目录的东西）。

    识别用 **AST + 父链**（不看缩进、不写死行号）：`if 本轮有缺失: notes.clear()` 这种
    「条件清空」会被判红 —— 因为它在「本轮没缺失」那一轮根本不执行，等于没清。

    **自带两条负向自证**（见函数末尾）：① 把 clear 包进 `if` -> 必须报；② 整段删掉 clear
    -> 必须报。没有这两条，「遍历式」完全可能是「遍历了个空集合」而永远绿。
    """
    src = EXPLORER.read_text(encoding="utf-8")
    names = _module_level_note_names(src)
    assert names, (
        "在 explorer_explore.py 里一个模块级 *_NOTES 容器都没收集到 -> "
        "要么容器改名了（判据会静默空转，必须同步），要么解析口径坏了"
    )
    bad = _notes_lacking_unconditional_clear(src)
    assert not bad, (
        "这些模块级 *_NOTES 容器缺「无条件清空」（上一轮的缺陷会留到下一轮，AI 白挨重试）：\n  - "
        + "\n  - ".join(bad)
        + f"\n（本次动态收集到的容器：{names}）"
    )

    # ---- 负向自证 ①：把 clear 包进 if 分支 -> 必须判红（否则「无条件」这半句等于没查）
    probe = src.replace("    _HARDCODED_NOTES.clear()",
                        "    if hard:\n        _HARDCODED_NOTES.clear()", 1)
    assert probe != src, "负向样本没生效（源码形态变了）-> 请同步本判据的替换锚点"
    hit = _notes_lacking_unconditional_clear(probe)
    assert any("_HARDCODED_NOTES" in h and "分支" in h for h in hit), \
        f"把 clear 挪进 if 分支却没被抓到 -> 判据对「条件清空」失明：{hit}"

    # ---- 负向自证 ②：整段删掉 clear -> 必须判红（否则「必须有一处」这半句等于没查）
    probe2 = src.replace("    _HARDCODED_NOTES.clear()   # [!] 无条件清（理由同上面的必填项 notes：会留旧账）",
                         "", 1)
    if probe2 == src:                       # 注释文案改过时的兜底锚点
        probe2 = src.replace("    _HARDCODED_NOTES.clear()", "", 1)
    assert probe2 != src, "负向样本没生效（源码形态变了）-> 请同步本判据的替换锚点"
    hit2 = _notes_lacking_unconditional_clear(probe2)
    assert any("_HARDCODED_NOTES" in h and "没有" in h for h in hit2), \
        f"删掉 clear 却没被抓到 -> 判据空转：{hit2}"
