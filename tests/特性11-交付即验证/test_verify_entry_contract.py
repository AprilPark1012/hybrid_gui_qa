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


# [!] V8.6.4（合并重复判据 · 第一批）：原 `test_replay_mode_does_not_retry` 只要求
# 「`录像回放模式：重试无意义` 在 cli.py 里**出现 >= 1 次**」—— 而两档是**各自独立**跳过回放的
# （产出档 `break` 出产出重试循环 / 实跑档 `raise SystemExit(3)`），所以**删掉任一档的那处都不会红**：
# 剩下那一处照样让"至少 1 次"成立。等价的弱兜底判据由此换成下面这条**强判据**。
# "回放不重试"的**行为面**（重试判定点附近能看到回放分支）仍由特性2 的
# `test_replay_mode_skips_retry` 守着；这条补的是**两档各自都在**这件事。

_REPLAY_NEEDLE = "录像回放模式：重试无意义"


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


def test_replay_is_skipped_in_both_retry_paths():
    """回放不重试：**两档各自**都要显式跳过 —— 出现 >= 2 次，且分别落在两个分支体内。

    为什么要有这条（V8.6.4）：旧判据只要"全文 >= 1 次"，删掉任一档都不会红 ——
    而两档的重试是**两条独立代码路径**（产出档：产出物被闸门拦下 -> 重生成；
    实跑档：脚本实跑失败 -> 整轮重来），各自的"回放则停"必须各自存在。

    两档的可区分特征（本判据据此钉"分落两档"）：
      · **产出档**（产出重试循环内）-> 该分支体第一条语句是 `break`（停掉产出重试循环）；
      · **实跑档**（L1 实跑失败后）-> 该分支体第一条语句是 `raise SystemExit(3)`（实跑未过 -> 退出码 3）。
    行号不写死（会偏移）：靠"该行所在分支体做了什么"识别，不看第几行。
    """
    src = (REPO / "framework" / "features" / "f10_cli" / "cli.py").read_text(encoding="utf-8", errors="replace")
    n = src.count(_REPLAY_NEEDLE)
    assert n >= 2, (
        f"「{_REPLAY_NEEDLE}」只出现 {n} 次 —— 产出档与实跑档必须**各自**显式跳过回放模式"
        f"（只堵一档时，另一档会白转 N 圈：回放的是同一份录像，转多少圈都是同一个坏产出）")
    branches = _replay_branches(src, _REPLAY_NEEDLE)
    assert len(branches) == n, (
        f"命中行数（{n}）与解析出的分支数（{len(branches)}）不一致 -> 解析写法要跟着代码改")
    for head, nxt in branches:
        assert "replay" in head, (
            f"「{_REPLAY_NEEDLE}」出现在 `{head}` 里 —— 它必须在**回放模式的分支**内"
            f"（写成无条件打印 = 回放模式真的会重试）")
    assert any(nxt.startswith("break") for _, nxt in branches), (
        f"产出档（产出物校验不合格 -> 重生成的重试循环）没有因回放而**停下**："
        f"命中分支 = {branches}")
    assert any(nxt.startswith("raise SystemExit(3)") for _, nxt in branches), (
        f"实跑档（L1 实跑失败 -> 整轮重来）没有因回放而跳过重试并如实退 3："
        f"命中分支 = {branches}")


def test_verify_failure_exit_codes_are_distinct():
    """两档失败的退出码必须能区分（产出侧 2 / 实跑侧 3），不许静默成功。"""
    src = (REPO / "framework" / "features" / "f10_cli" / "cli.py").read_text(encoding="utf-8", errors="replace")
    assert "raise SystemExit(2)" in src and "raise SystemExit(3)" in src, (
        "两档失败要有不同的非 0 退出码（产出物不合格 2 / 实跑未过 3）")
