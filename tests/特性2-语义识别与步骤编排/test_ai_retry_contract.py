# -*- coding: utf-8 -*-
"""特性2 · AI 产出的「校验 -> 自动重试」闭环（V8.4 · 用户 2026-10-08 选 B）。

[!] V8.6.4（合并重复判据 · 第二批 · 组 1 遗留）两处变动，**文件改名**
    `test_ai_retry_loop.py` -> **`test_ai_retry_contract.py`**（它现在守的是「上限 / 回炉 / 接线」这三条契约，
    早已不只是 loop）：

  1. **删掉 `test_same_reason_stops_retrying`**（原 :80-93）—— 它与同目录
     `test_ai_retry_same_cause.py` 守**同一件事**（失败原因没变就不重试），但那条**更强**：
     它走 `exec` 真函数体（连 `_retry_reason_fingerprint` 一起 exec）+ **指纹源码断言**，
     而本条只是把同样的输入再喂一遍 —— 「日志路径时间戳让同因判不出来」那个真实事故，
     旧版这条**抓不到**（它用的是手写短原因，没有路径）。
     接手 = `test_ai_retry_same_cause.py`（5 条：指纹忽略日志路径 / 真差异不许抹平 /
     走指纹比较 + 行为验证 / 换因仍重试 / 边界）。
  2. **`test_prompt_without_feedback_is_clean` 交给** `test_retry_feedback_contract.py`
     （V8.6.4 第二批 · 组 3 的合并文件），那里与质量警告通道的同类断言**取严**后并成一条
     `test_prompt_stays_clean_without_feedback`。

为什么需要（实测教训）：
    AI 编排是**非确定性**的。同一场景连续生成，逐轮暴露不同缺陷：
      · 第 1 轮：自己编登录流程 + 编造密码 `123456`（真值 super@123）-> 崩在第一步
      · 第 2 轮：`select` 猜选项 value `"1"` -> `did not find some options`
      · 第 4 轮：拿 `index`（host 片段）当换页证据 -> 假绿，被质量闸拦下
    **用「提示词逐条堵」能堵住每一条，但堵不完**。工程的解法是承认「一次生成就对」不可靠：
    把**已有**的校验能力（L0 静态质量闸 / L1 实跑校验）接成**有界重试** —— 不合格就带着
    **具体失败原因**让 AI 重生成，最多 N 次；仍不合格则如实报错（绝不静默当成功）。

设计要点（用户已审）：
    · 两级校验都重试，**便宜的先跑**（L0 静态毫秒级 -> L1 实跑几十秒）；
    · 重试次数 **默认 2**，`HYBRID_AI_RETRY` 可调，`0` = 关闭重试（退回旧行为）；
    · **同因不重试**（失败原因没变说明再问也白问，直接停，省 token）；
    · **录像回放模式跳过重试**（回放的是同一份录像，转 N 圈还是坏产出）；
    · **质量闸绝不弱化** —— 重试只是「多给几次机会」，不是「放宽标准」。

判据口径：纯函数 + 接线检查，不联网、不调真 LLM、不跑浏览器。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "framework" / "features" / "f10_cli" / "cli.py"
EXPLORER = REPO / "framework" / "features" / "f02_semantic" / "explorer_explore.py"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _fn_src(p: Path, name: str) -> str:
    src = _src(p)
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"{p.name} 里找不到 {name}()")


# ---------------------------------------------------------------- 重试上限（纯函数）

def test_retry_limit_default_is_two():
    """默认重试 2 次（用户审定：兼顾成功率与耗时/token）。"""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.cli import _ai_retry_limit

    assert _ai_retry_limit({}) == 2, "默认重试次数应为 2"


def test_retry_limit_configurable_and_zero_disables():
    """`HYBRID_AI_RETRY` 可调；`0` = 关闭重试（必须能退回旧行为，否则出问题没法止血）。"""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.cli import _ai_retry_limit

    assert _ai_retry_limit({"HYBRID_AI_RETRY": "0"}) == 0
    assert _ai_retry_limit({"HYBRID_AI_RETRY": "5"}) == 5


def test_retry_limit_is_bounded_and_forgiving_of_garbage():
    """脏值不许让整条链路崩（环境变量是人手敲的），要有上界防「重试到天荒地老」。"""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.cli import _ai_retry_limit

    assert _ai_retry_limit({"HYBRID_AI_RETRY": "abc"}) == 2, "脏值应回落到默认值，而不是抛异常"
    assert _ai_retry_limit({"HYBRID_AI_RETRY": "-3"}) == 0
    assert _ai_retry_limit({"HYBRID_AI_RETRY": "999"}) <= 5, "必须有上界（否则一次跑可能烧掉几十次 LLM 调用）"


# ---------------------------------------------------------------- 失败原因进提示词
#
# [!] V8.6.4：原「同因不重试」一条（test_same_reason_stops_retrying）已删 —— 接手 =
#     tests/特性2-语义识别与步骤编排/test_ai_retry_same_cause.py（更强：走真函数体 exec +
#     指纹源码断言，覆盖「日志路径时间戳让同因判不出来」那个真实事故）。

def test_prompt_accepts_retry_feedback():
    """提示词必须能接收「上一轮为什么不合格」——否则重试只是再掷一次骰子。"""
    body = _fn_src(EXPLORER, "_build_planner_prompt")
    head = body[: body.index(") -> str:") + 1]
    assert "retry_feedback" in head, (
        "_build_planner_prompt 没有 retry_feedback 参数 —— 重试无法把失败原因告诉 AI"
    )


def test_prompt_includes_retry_feedback_text():
    """传了失败原因，它必须真的出现在提示词里（且醒目：告诉 AI 这是**上次被拦**的原因）。"""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.features.f02_semantic.explorer_explore import _build_planner_prompt

    txt = "换页证据 'index' 只是 host[:端口]，跨页用例里每个页面都含它"
    prompt = _build_planner_prompt("随便", [], "http://x/", auth={"username": "u"},
                                   retry_feedback=txt)
    assert txt in prompt.replace("\n", " ").replace("  ", " ") or "换页证据" in prompt, (
        "失败原因没有出现在提示词里 —— AI 不知道上次错在哪"
    )
    flat = prompt.replace("\n", "")
    assert any(w in flat for w in ("上一轮", "上次", "重试", "被拦")), (
        "提示词没有标明这段是「上一次失败的原因」—— AI 可能把它当普通背景读过去"
    )


# [!] V8.6.4（第二批 · 组 3）：原 `test_prompt_without_feedback_is_clean` **已删** ——
#     接手 = tests/特性2-语义识别与步骤编排/test_retry_feedback_contract.py
#     `::test_prompt_stays_clean_without_feedback`（与「质量警告通道」的同类断言**取严**合并：
#     `"上一轮" not in flat` 与 `"上一轮框架识别出的" not in prompt` 两条都查）。
#     删的理由：两条判据守同一件事（「不给反馈时提示词里不许凭空出现回炉字样」），
#     被接手那条更强 -> 本文件不再保留第二份。


# ---------------------------------------------------------------- 接线

def test_explore_has_retry_loop():
    """接线判据：`cmd_explore` 里必须真的有重试循环（写了函数不接线等于没有）。"""
    body = _fn_src(CLI, "cmd_explore")
    assert "_ai_retry_limit(" in body, "cmd_explore 没有读重试上限 -> 重试闭环没接上"
    assert "_should_retry_again(" in body, "cmd_explore 没有用「同因不重试」判定"


def test_replay_mode_skips_retry():
    """录像回放模式必须跳过重试 —— 回放的是同一份录像，转 N 圈还是同一个坏产出。"""
    body = _fn_src(CLI, "cmd_explore")
    i = body.find("_should_retry_again(")
    assert i != -1
    # 判定点附近必须能看到回放模式的判断
    seg = body[max(0, i - 1200): i + 600]
    assert "is_replay" in seg or "回放" in seg, (
        "重试判定附近没有「回放模式跳过重试」的分支 —— 录像回放会白转 N 圈"
    )



# [!] V8.6.4（合并重复判据 · 第一批）：删掉原 `test_quality_gate_not_weakened` —— 它是**假绿兜底**：
# 断言写成 `... or "SystemExit(2)" in src`，而 `src` 取的是**整个 cli.py**，"SystemExit(2)" 全文有
# **20 处** -> 后半句恒真：前半句（真去 `_report_case_quality` 里找 exit 2）坏掉了也不会红。
# 它想守的语义（假绿红线必须真 exit 2、重试不许以弱化闸门为代价）已由
# `tests/特性11-交付即验证/test_verify_entry_contract.py::test_verify_failure_exit_codes_are_distinct`
# **完整**覆盖（那里钉的是两档退出码真的存在且可区分：`raise SystemExit(2)` + `raise SystemExit(3)`）。
