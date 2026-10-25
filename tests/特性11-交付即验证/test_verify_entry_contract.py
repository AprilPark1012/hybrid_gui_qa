# -*- coding: utf-8 -*-
"""特性11 · 「交付即验证」入口契约（P25 片 1 · 判据先行，V8.5）

## 为什么有这一条（AprilPark1012 2026-10-11 要求5）

`verify` 要**从 explore 里独立出来成为单独一个特性**：它是「交付即验证」的基础 ——
产出物不合格就带原因重生成、脚本生成后真跑一次、失败了带原因整轮重来。

现状（V8.6.4 校准；片 1 基线那句"应当红"是当时的，今天已全绿 —— 过期文案本身就是漂移）：
- CLI **有** `verify` 子命令（两档重试的实现住在 `framework/features/f10_cli/cli.py`：
  产出档重试循环 + 实跑档（L1）重试，两处各自显式跳过录像回放模式）；
- `all` **接受** `--ai`（要求4：`python -m framework.cli all [--ai]` 是统一入口），
  并把 `--scenario` / `--scenario-file` / `--scenario-dir` 传下去。

## 口径（两档 + 有界 + 回放不重试）

1. **产出物档**：AI 产出被闸门拦下 -> 带**具体原因**让 AI 重生成（有界：`HYBRID_AI_RETRY`，默认 2、上界 5）；
2. **实跑档**：`generate` 脚本 + 逐条实跑 -> 失败带原因整轮重来（同一上界）；
3. **录像回放模式下不重试**（回放的是同一份录像，转圈无意义 —— 现状已是此口径，要保住）；
4. 退出码：产出侧不合格 = 2；实跑未过 = 3（不许静默成功）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from framework.features.f10_cli import cli   # P25 片 8：patch 要打在**真实现**上（framework.cli 现在是转发薄壳）

REPO = Path(__file__).resolve().parents[2]


def test_cli_has_verify_subcommand():
    """CLI 必须有独立的 verify 子命令（两档验证的入口）。"""
    cmds = set(getattr(cli, "CMD_FLAGS", {}))
    assert "verify" in cmds, (
        f"缺 `verify` 子命令（现有：{sorted(cmds)}）。要求5：verify 是独立特性 ——"
        "产出物重试 + 实跑重试两档要有自己的入口，不能被塞在 explore 里")


def test_all_accepts_ai_flag():
    """`all` 必须接受 --ai（要求4：命令统一，用是否带 --ai 区分两条链路）。"""
    flags = set(getattr(cli, "CMD_FLAGS", {}).get("all", set()))
    assert "--ai" in flags, (
        f"`all` 不接受 --ai（现有：{sorted(flags)}）。"
        "真 AI 链路应当是 `python -m framework.cli all --ai`，而不是只能单跑 explore")


def test_all_accepts_scenario_flags_when_ai():
    """`all --ai` 要能把场景传下去（否则 AI 链路没法表达跑哪个场景）。"""
    flags = set(getattr(cli, "CMD_FLAGS", {}).get("all", set()))
    need = {"--scenario", "--scenario-file", "--scenario-dir"}
    missing = sorted(need - flags)
    assert not missing, f"all 缺场景参数：{missing}（AI 链路要能指定场景）"


# [!] V8.6.4（合并重复判据 · 第一批）：删掉原 `test_retry_is_bounded` ——
# 它断言的三件事（999 -> <=5 有上界 / 0 = 关闭 / 缺省 = 2）**逐条**被
# `tests/特性2-语义识别与步骤编排/test_ai_retry_contract.py` 严格覆盖，后者多了两件它没有的：
#   · 脏值回落（`HYBRID_AI_RETRY="abc"` 不许抛异常 -> 回落默认 2）
#   · 负值（`-3` -> 0）
# （[!] 第二批把那个文件由 `test_ai_retry_loop.py` 改名为 `test_ai_retry_contract.py` ——
#  R9 搬家协议：这里指旧位置的地方要跟着改。）
# 同一个 `_ai_retry_limit` 的口径只有一份，判据也只留一份（在特性2，与实现同特性）。


# [!] V8.7.2（2026-10-25）：契约**变更** —— 原判据 `test_replay_is_skipped_in_both_retry_paths`
# 要求两档各自「因回放而停下」（产出档 `break` / 实跑档 `raise SystemExit(3)`），
# 依据是「回放的是同一份录像，转 N 圈还是同一个坏产出」。**这个前提不成立**：
#   重试会把本轮失败原因写进 feedback（见 `_next_round_feedback`）-> **下一轮 prompt 必然是新的**；
#   录像包若录了那一轮（「失败→修复」闭环，本项目 orders_invoice_full_lifecycle 实测就是这样：
#   第 1 轮缺「两步保存」-> 实跑 FAILED；第 2 轮带失败原因重生成 -> PASSED），就该继续推进。
#   旧口径让这份录像包**永远回放不通** —— 而「失败→修复」恰恰最需要在无外网机器上复演。
#
# [!] 原判据要防的「白转 N 圈」**并未放松**，改由这条新判据的两个条件覆盖：
#   (a) 仍受 `_should_retry_again` 有界约束（非同因、次数用尽即停）；
#   (b) 缺录像 -> `CassetteError` -> **exit 2 明确报缺**，根本不进第二圈。
# 旧口径的字符串 `重试无意义` 必须**彻底消失**（残留 = 行为没真改）。
_REPLAY_NEEDLE = "回放模式：带"


def _replay_branches(src: str, needle: str) -> list[tuple[str, str]]:
    """每个含 needle 的行 -> (它**所在分支的判定头**, 该分支里的**下一条语句**)。

    [!] 为什么不能只看"下面缩进更深的第一行"（第一版就是这么写错的，判据当场红）：
    `print(needle)` 与紧跟的 `break` / `raise SystemExit(3)` 是**同一层**的兄弟语句，
    不存在"更深"的下一行 -> 那个写法永远收集不到东西（红得莫名其妙）。
    正解分两步，都按**缩进**判、不写死行号：
      · 往上找**最近的、缩进更浅且以 `:` 结尾**的行 = 它所在分支的判定头（如 `if replay:`）；
      · 再往下取同层或更深的**第一条语句**（空行与注释跳过）= 该分支随后做了什么。
    """
    lines = src.splitlines()
    out: list[tuple[str, str]] = []
    for i, line in enumerate(lines):
        if needle not in line:
            continue
        base = len(line) - len(line.lstrip())
        head = ""
        for j in range(i - 1, -1, -1):
            s = lines[j]
            if not s.strip() or s.strip().startswith("#"):
                continue
            if len(s) - len(s.lstrip()) < base and s.rstrip().endswith(":"):
                head = s.strip()
            break                       # 只认"紧邻的上一条语句"是不是分支头（跳过后即停）
        nxt = ""
        for j in range(i + 1, len(lines)):
            s = lines[j]
            if not s.strip() or s.strip().startswith("#"):
                continue
            if len(s) - len(s.lstrip()) < base:
                break                   # 缩进更浅 = 分支体到此为止（本条是分支体最后一句）
            nxt = s.strip()
            break
        out.append((head, nxt))
    return out


def test_replay_advances_to_next_round_in_both_retry_paths():
    """回放**允许**推进到下一轮（两档各自），且缺录像必须 fail loud —— 不再一刀切跳过。

    契约（V8.7.2 变更，理由见本文件上方长注释）：录制期必然先失败一轮、第 2 轮才修好；
    重试会把失败原因写进 prompt -> 下一轮 prompt 与录制那轮**不同**，录像若录了那一轮就该推进。

    判据四条（缺一不可）：
      (1) 旧口径 `重试无意义` **彻底消失** —— 残留即行为没真改；
      (2) 两档**各自**都有回放分支说明（>= 2 处），且分支头是 `if replay:`；
      (3) 那些分支体**不许**是 `break` / `raise SystemExit(3)` —— 回放不再因失败而停下；
      (4) 「白转」防线换了位置：缺录像必须由 `except (AiExploreError, CassetteError)` 接住并退 2，
          外加仍受 `_should_retry_again` 的有界约束（不是无条件重试）。
    行号不写死（会偏移）：靠缩进解析分支头与分支体首条语句。
    """
    src = (REPO / "framework" / "features" / "f10_cli" / "cli.py").read_text(encoding="utf-8", errors="replace")

    assert "重试无意义" not in src, (
        "旧口径「重试无意义」仍留在 cli.py 里 —— 回放遇到失败后仍会一刀切停下，"
        "「失败→修复」闭环不可离线复演")

    n = src.count(_REPLAY_NEEDLE)
    assert n >= 2, (
        f"「{_REPLAY_NEEDLE}」只出现 {n} 次 —— 产出档（L0 校验不合格）与实跑档（L1 实跑失败）"
        f"必须**各自**说明「带失败原因去找下一轮的录像」，只写一档时删掉另一档也不会红")

    branches = _replay_branches(src, _REPLAY_NEEDLE)
    assert len(branches) == n, (
        f"命中行数（{n}）与解析出的分支数（{len(branches)}）不一致 -> 解析写法要跟着代码改")
    for head, nxt in branches:
        assert "replay" in head, (
            f"「{_REPLAY_NEEDLE}」出现在 `{head}` 里 —— 它必须在**回放模式的分支**内"
            f"（写成无条件打印 = 非回放模式也被这段文案误导）")
        assert not nxt.startswith("break"), (
            f"回放分支体是 `break`（因回放而停下重试循环）：{head} -> {nxt}")
        assert not nxt.startswith("raise SystemExit(3)"), (
            f"回放分支体是 `raise SystemExit(3)`（因回放而整体退出）：{head} -> {nxt}")

    assert "_should_retry_again(" in src, (
        "没在 _should_retry_again 闸门内推进 —— 回放会变成**无条件重试**（原判据要防的「白转 N 圈」）")
    assert "except (AiExploreError, CassetteError)" in src, (
        "没把 CassetteError 一并接住 —— 回放允许重试后，第二轮缺录像会抛**未捕获 traceback**"
        "（CassetteError 与 AiExploreError 是兄弟类，不是父子）")
    assert "回放缺这一轮的录像" in src, (
        "缺录像时没有明确报出「缺的是哪一轮」—— 只说「没有这一份」等于让人猜")


def test_verify_failure_exit_codes_are_distinct():
    """两档失败的退出码必须能区分（产出侧 2 / 实跑侧 3），不许静默成功。"""
    src = (REPO / "framework" / "features" / "f10_cli" / "cli.py").read_text(encoding="utf-8", errors="replace")
    assert "raise SystemExit(2)" in src and "raise SystemExit(3)" in src, (
        "两档失败要有不同的非 0 退出码（产出物不合格 2 / 实跑未过 3）")
