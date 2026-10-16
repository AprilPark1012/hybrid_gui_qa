# -*- coding: utf-8 -*-
"""特性2 · 「上一轮识别出的质量警告」必须喂回下一轮生成提示词（C4 · 2026-10-16）。

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
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from framework.cli import _next_round_feedback, _quality_warn_feedback  # noqa: E402
from framework.features.f02_semantic.explorer_explore import _build_planner_prompt  # noqa: E402

CLI = ROOT / "framework" / "features" / "f10_cli" / "cli.py"

#: 与实测日志同形的假警告（带控件名 / 步骤号这类可操作信息）
_FIXTURE = [
    "[行内控件缺行定位（多匹配）] 控件 '数量@开票页' 重复出现 3 个 -> 运行期必红",
    "有 1 个操作步骤没有绑定元素（element 为空）→ 生成脚本定位不到，执行必然失败：click（提交整个订单）",
    "跨页用例里这些声明过的页面既没有 goto 也没有 url 断言作为到达证据：['http://x/invoice_list.html']",
]


def _fn_src(path: Path, name: str) -> str:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"{path.name} 里找不到 {name}()")


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
    """没警告、没硬原因时提示词里不许出现回炉段落（与既有 test_prompt_without_feedback_is_clean 同口径）。"""
    prompt = _build_planner_prompt("随便什么场景", [], "http://127.0.0.1:8000/")
    assert "上一轮框架识别出的" not in prompt, "没给警告却出现了「上一轮有质量问题」段落"
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
    from framework.features.f02_semantic import explorer_explore as EX

    EX.SEMANTIC_MISMATCH_NOTES.clear()
    try:
        warns = _ai_gate_warn_entries()
        assert warns == [], f"清单为空却读出条目：{warns}"
        EX.SEMANTIC_MISMATCH_NOTES.append("第 3 步「打开菜单」选的控件与描述重叠度 0.00(几乎无关)")
        assert _ai_gate_warn_entries() == [], "BLOCK 级问题被当成警告重复收集了（它已走硬拦截）"
    finally:
        EX.SEMANTIC_MISMATCH_NOTES.clear()
    # WARN 级（当前是「行内控件缺行定位」）必须读得出来
    EX._ROW_SCOPE_NOTES.append("控件 '数量@开票页' 重复出现 3 个（行内控件缺行定位）")
    try:
        got = _ai_gate_warn_entries()
        assert any("数量@开票页" in x for x in got), f"WARN 级条目没读出来：{got}"
    finally:
        EX._ROW_SCOPE_NOTES.clear()
