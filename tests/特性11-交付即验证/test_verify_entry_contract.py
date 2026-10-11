# -*- coding: utf-8 -*-
"""特性11 · 「交付即验证」入口契约（P25 片 1 · 判据先行，V8.5）

## 为什么有这一条（AprilPark1012 2026-10-11 要求5）

`verify` 要**从 explore 里独立出来成为单独一个特性**：它是「交付即验证」的基础 ——
产出物不合格就带原因重生成、脚本生成后真跑一次、失败了带原因整轮重来。

现状（片 1 基线，本判据**应当红**）：
- CLI **没有** `verify` 子命令（两档重试内嵌在 `cmd_explore` 里，cli.py:671-733 + 746-876）；
- `all` **不接受** `--ai`（要求4：`python -m framework.cli all [--ai]` 才是统一入口）。

## 口径（两档 + 有界 + 回放不重试）

1. **产出物档**：AI 产出被闸门拦下 -> 带**具体原因**让 AI 重生成（有界：`HYBRID_AI_RETRY`，默认 2、上界 5）；
2. **实跑档**：`generate` 脚本 + 逐条实跑 -> 失败带原因整轮重来（同一上界）；
3. **录像回放模式下不重试**（回放的是同一份录像，转圈无意义 —— 现状已是此口径，要保住）；
4. 退出码：产出侧不合格 = 2；实跑未过 = 3（不许静默成功）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from framework import cli

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


def test_retry_is_bounded():
    """重试必须有界（防手滑写成 999 把 token 烧光）。"""
    fn = getattr(cli, "_ai_retry_limit", None)
    assert callable(fn), "缺 _ai_retry_limit（重试次数的唯一口径）"
    assert fn({"HYBRID_AI_RETRY": "999"}) <= 5, "重试上界必须存在且 <= 5"
    assert fn({"HYBRID_AI_RETRY": "0"}) == 0, "0 必须表示关闭（退回旧行为）"
    assert fn({}) == 2, "默认值应为 2"


def test_replay_mode_does_not_retry():
    """回放模式下不重试（回放的是同一份录像，转圈无意义）。"""
    src = (REPO / "framework" / "cli.py").read_text(encoding="utf-8", errors="replace")
    assert "录像回放模式：重试无意义" in src, (
        "两条重试路径都必须显式跳过回放模式（cli.py 现在有两处：产出档 + 实跑档）")


def test_verify_failure_exit_codes_are_distinct():
    """两档失败的退出码必须能区分（产出侧 2 / 实跑侧 3），不许静默成功。"""
    src = (REPO / "framework" / "cli.py").read_text(encoding="utf-8", errors="replace")
    assert "raise SystemExit(2)" in src and "raise SystemExit(3)" in src, (
        "两档失败要有不同的非 0 退出码（产出物不合格 2 / 实跑未过 3）")
