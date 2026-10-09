# -*- coding: utf-8 -*-
"""特性2 · AI 产出的「校验 -> 自动重试」闭环（V8.4 · 用户 2026-10-08 选 B）。

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
CLI = REPO / "framework" / "cli.py"
EXPLORER = REPO / "framework" / "tools" / "explore" / "explorer.py"


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


# ---------------------------------------------------------------- 同因不重试

def test_same_reason_stops_retrying():
    """失败原因没变 -> 停（再问也是同一个答案，白烧 token）。"""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.cli import _should_retry_again

    assert _should_retry_again(prev="假绿：换页证据用 index", new="假绿：换页证据用 index",
                               attempt=0, limit=2) is False
    assert _should_retry_again(prev="假绿：换页证据用 index", new="缺 value 的步骤渲染崩",
                               attempt=0, limit=2) is True
    # 第一轮没有 prev，必须允许重试
    assert _should_retry_again(prev="", new="任意原因", attempt=0, limit=2) is True
    # 次数用尽 -> 不许再试
    assert _should_retry_again(prev="a", new="b", attempt=2, limit=2) is False


# ---------------------------------------------------------------- 失败原因进提示词

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
    from framework.tools.explore.explorer import _build_planner_prompt

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


def test_prompt_without_feedback_is_clean():
    """**负向的另一面**：不给失败原因时，不许凭空出现「上一轮失败」这类字样（避免误导）。"""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.tools.explore.explorer import _build_planner_prompt

    prompt = _build_planner_prompt("随便", [], "http://x/", auth={"username": "u"})
    flat = prompt.replace("\n", "")
    assert "上一轮" not in flat, "没重试却出现了「上一轮」字样 —— 会误导 AI 以为自己做错过"


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


def test_quality_gate_not_weakened():
    """**底线判据**：质量闸不许因为「要重试」而被弱化（该拦还得拦、该 exit 还得 exit）。"""
    src = _src(CLI)
    assert "raise SystemExit(2)" in _fn_src(CLI, "_report_case_quality") or "SystemExit(2)" in src, (
        "假绿红线不再 exit 2 了 —— 重试不能以弱化闸门为代价"
    )
