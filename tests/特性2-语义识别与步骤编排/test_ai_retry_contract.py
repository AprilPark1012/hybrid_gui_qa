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
    · **录像回放模式同样可以重试到下一轮**（V8.7.2 变更：重试会把失败原因写进 prompt，
      下一轮 prompt 就不是「同一份」了；录像若录了那一轮就该推进，否则「失败→修复」
      永远不可离线复演。缺录像由 CLI 退 2 明确报缺，不静默降级）；
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


def test_replay_mode_has_explicit_branch_near_retry_gate():
    """回放模式在**重试判定点附近**必须有显式分支 —— 但不再要求它「跳过重试」。

    历史（V8.7.2 变更）：原判据 `test_replay_mode_skips_retry` 断言「回放必须跳过重试」，
      理由是「回放的是同一份录像，转 N 圈还是坏产出」。实测推翻了这个前提：重试会把
      失败原因写进 prompt（`_next_round_feedback`）-> 下一轮 prompt 是**新的**，录像若录了
      那一轮就该推进，否则「失败→修复」闭环永远不可离线复演。

    本判据的**分工**（避免与特性11 重复判据）：
      · 这里只守**行为面**：回放与非回放的行为差异在重试判定点附近有显式说明（不是靠巧合）；
      · 「分支体不许 break / SystemExit(3)」「缺录像必须退 2」由特性11 的
        `test_replay_advances_to_next_round_in_both_retry_paths` 用强判据（源码结构解析）守。
    """
    body = _fn_src(CLI, "cmd_explore")
    i = body.find("_should_retry_again(")
    assert i != -1
    seg = body[max(0, i - 1200): i + 600]
    assert "is_replay" in seg or "回放" in seg, (
        "重试判定附近看不到回放模式的分支 —— 回放与非回放的行为差异没有任何显式说明"
    )
    assert "重试无意义" not in body, (
        "旧口径「重试无意义」残留 —— 回放遇到失败仍会一刀切停下，「失败→修复」不可离线复演"
    )



# [!] V8.6.4（合并重复判据 · 第一批）：删掉原 `test_quality_gate_not_weakened` —— 它是**假绿兜底**：
# 断言写成 `... or "SystemExit(2)" in src`，而 `src` 取的是**整个 cli.py**，"SystemExit(2)" 全文有
# **20 处** -> 后半句恒真：前半句（真去 `_report_case_quality` 里找 exit 2）坏掉了也不会红。
# 它想守的语义（假绿红线必须真 exit 2、重试不许以弱化闸门为代价）已由
# `tests/特性11-交付即验证/test_verify_entry_contract.py::test_verify_failure_exit_codes_are_distinct`
# **完整**覆盖（那里钉的是两档退出码真的存在且可区分：`raise SystemExit(2)` + `raise SystemExit(3)`）。


# ---------- 重试日志必须能区分「哪一档」和「总共第几次」（V8.7.4，2026-10-26 实测事故）----------
# 事故：L0（产出物档）和 L1（实跑档）各有独立计数器，各自从 0 起、各自 +1 后**都打印 "2/3"**
#   -> 用户日志里看到「重试第一次和重试第二次是同一句话」，误以为计数没递增。
#   数字没算错，错在两条日志长得一样：分不清哪档在重试、也数不出总共重试了几次。

_CLI_SRC = (REPO / "framework" / "features" / "f10_cli" / "cli.py").read_text(
    encoding="utf-8", errors="replace")


def test_retry_logs_carry_level_tags():
    """两条重试日志必须各带档位标签 —— 没有标签就分不清是 L0 还是 L1。"""
    assert "[L0 产出物档]" in _CLI_SRC, "L0 重试日志缺档位标签"
    assert "[L1 实跑档]" in _CLI_SRC, "L1 重试日志缺档位标签"


def test_retry_logs_are_not_identical_text():
    """两条重试日志的**文本必须不同** —— 这是本事故的最小复现形态。

    原来两条都只写「（第 k/N 次）」，k/N 还各自从 0 起算 -> 打出来一模一样。
    """
    import re

    m0 = re.search(r'\[L0 产出物档\][^"]*', _CLI_SRC)
    m1 = re.search(r'\[L1 实跑档\][^"]*', _CLI_SRC)
    assert m0 and m1, "两条档位日志没找到"
    assert m0.group().strip() != m1.group().strip(), "L0 与 L1 的日志文本仍然相同"


def test_retry_logs_show_level_count_and_cumulative_total():
    """每条重试日志都要同时给「该档第 k/N」和「累计第 M 次」——
    前者说明这一档还剩几次机会，后者让人一眼数出整轮到底重试了几次。

    [!] 不能只匹配 `[L0 产出物档][^"]*` 那种单行正则：源码里这条日志是**两行 f-string 拼接**的，
       `[^"]*` 到第一个引号就停，取不到第二行的 `{retry_seq}`（写完第一版就这么假红过）。
       所以直接数全仓出现次数：L0 和 L1 各必须有一处。
    """
    needle = "累计第 {retry_seq} 次重试"
    n = _CLI_SRC.count(needle)
    assert n >= 2, f"「累计第 M 次重试」只出现 {n} 处，应 ≥2（L0 与 L1 各一处）"

    # 两档各自的「该档第 k/N」也必须都在
    assert "{attempt + 1}/{retry_limit + 1} 次" in _CLI_SRC, "L0 缺「该档第 k/N 次」"
    assert "{l1_attempt + 1}/{retry_limit + 1} 轮" in _CLI_SRC, "L1 缺「该档第 k/N 轮」"


def test_retry_seq_is_shared_across_levels():
    """`retry_seq` 必须是**跨档共享**的一个变量：定义在 `while True:` 之前，且两档都 += 1。

    若哪天有人把它改成各档自己的局部变量，这个 bug 就会原样复活。
    """
    import ast

    tree = ast.parse(_CLI_SRC)
    # 找到包含 retry_seq 的那个函数
    target_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            if "retry_seq" in names and "l1_attempt" in names:
                target_fn = node
                break
    assert target_fn is not None, "没找到同时用 retry_seq 和 l1_attempt 的函数"

    # ① 函数体内必须有 `retry_seq = 0` 赋值
    has_init = False
    for node in ast.walk(target_fn):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and node.value.value == 0:
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "retry_seq":
                    has_init = True
    assert has_init, "retry_seq 没有在函数内初始化为 0"

    # ② 必须有 `retry_seq += 1` 至少两处（L0 一处、L1 一处）
    inc = 0
    for node in ast.walk(target_fn):
        if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add) \
                and isinstance(node.target, ast.Name) and node.target.id == "retry_seq":
            inc += 1
    assert inc >= 2, f"retry_seq 自增只有 {inc} 处，应 ≥2（L0 与 L1 各一处）"

    # ③ 初始化行号必须早于第一次 += （否则计数会从错的地方开始）
    init_line = min(
        n.lineno for n in ast.walk(target_fn)
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
        and n.value.value == 0
        and any(isinstance(t, ast.Name) and t.id == "retry_seq" for t in n.targets)
    )
    first_inc_line = min(
        n.lineno for n in ast.walk(target_fn)
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name)
        and n.target.id == "retry_seq"
    )
    assert init_line < first_inc_line, (
        f"retry_seq 初始化（行 {init_line}）必须早于首次自增（行 {first_inc_line}）"
    )
