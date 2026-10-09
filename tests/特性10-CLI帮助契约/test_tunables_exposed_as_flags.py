# -*- coding: utf-8 -*-
"""特性10 · 常用可调项必须能从命令行直接给（V8.4 · 用户 2026-10-08 定「方案 2」）。

背景（用户提问引出）：
    框架里有 **41 个 `HYBRID_*` 环境变量**，但：
      · `.env.example` 里**一个都没有** -> 用户**不知道它们存在**；
      · 项目 `.env` **不入库、现状压根不存在** -> 「设在那里」等于「每个使用者自己去猜、去建一个不在仓库里的文件」；
      · shell 里 export 要会敲命令、且只在当次会话有效。
    -> 用户结论（verbatim）：「可以用CLI参数」。选定方案 2：
      **常用项开成 CLI 参数；全部可调项用 `cli config` 列出（含当前值与来源）**；
      **不引入第二套配置文件**（避免与 env 并存造成「双入口」，违反「同一能力收敛成唯一入口」）。

判据口径：
  · 分层：**用户会调的** 必须有 CLI 参数；**框架运行期自设的**（RUN_ID / PARTITION / W …）**反面判据** ——
    不许给用户开参数（开了就是误导）；
  · 优先级必须明确：**CLI > 环境变量 > 默认**；
  · `--help` 必须自动覆盖新参数（项目既有契约：特性 10.3）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "framework" / "cli.py"


def _src() -> str:
    return CLI.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 必须开成 CLI 参数

#: 用户会调的项 -> (CLI 参数名, 对应的环境变量名, 该参数属于哪些子命令)
USER_TUNABLE = [
    ("--ai-retry", "HYBRID_AI_RETRY", {"explore"}),
    ("--shots", "HYBRID_SHOTS", {"run", "all"}),
    ("--video", "HYBRID_VIDEO", {"run", "all"}),
    ("--timeout", "HYBRID_CASE_TIMEOUT", {"run", "all"}),
    ("--base-url", "HYBRID_BASE_URL", {"run", "all", "probe", "generate"}),
    ("--strict-locate", "HYBRID_STRICT_LOCATE", {"run", "all"}),
]


@pytest.mark.parametrize("flag,envvar,cmds", USER_TUNABLE)
def test_tunable_has_cli_flag(flag: str, envvar: str, cmds: set[str]):
    """每个「用户会调」的项都要有对应的 CLI 参数（否则只能改环境变量 —— 不可发现）。"""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.cli import FLAG_SPECS

    assert flag in FLAG_SPECS, (
        f"{flag} 没有登记进 FLAG_SPECS —— 用户没法在命令行上调 {envvar}（只能改环境变量，不可发现）"
    )


@pytest.mark.parametrize("flag,envvar,cmds", USER_TUNABLE)
def test_tunable_flag_available_on_right_commands(flag: str, envvar: str, cmds: set[str]):
    """参数必须挂在**正确的子命令**上（挂错=用不上；挂太多=污染别的命令的帮助）。"""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.cli import CMD_FLAGS

    for c in cmds:
        assert flag in CMD_FLAGS.get(c, set()), f"{c} 子命令上没挂 {flag}（对应 {envvar}）"


def test_ai_retry_flag_takes_value():
    """`--ai-retry` 必须带值（`--ai-retry 3`），不是纯开关。"""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.cli import FLAG_SPECS

    assert FLAG_SPECS.get("--ai-retry") == "value", "--ai-retry 必须带值"


def test_user_tunables_reachable_from_envvar_names():
    """反查判据：`config` 命令要用的「参数 -> 环境变量」映射必须存在且完整。

    没有这个映射，`cli config` 就没法告诉用户「这一项怎么在命令行上调」。
    """
    import sys
    sys.path.insert(0, str(REPO))
    from framework.cli import ENV_TO_FLAG

    for flag, envvar, _ in USER_TUNABLE:
        assert ENV_TO_FLAG.get(envvar) == flag, f"{envvar} 没有映射到 {flag}"


# ---------------------------------------------------------------- 反面判据（别乱开）

def test_internal_only_vars_have_no_cli_flag():
    """**反面判据**：框架运行期**自设**的变量不许开 CLI 参数 —— 开了就是骗用户。

    `HYBRID_RUN_ID` / `HYBRID_PARTITION` / `HYBRID_W` 是框架给每个 worker / 每次 run 分配的，
    用户设了也只会把链路搞乱。
    """
    import sys
    sys.path.insert(0, str(REPO))
    from framework.cli import ENV_TO_FLAG

    for internal in ("HYBRID_RUN_ID", "HYBRID_PARTITION", "HYBRID_W"):
        assert internal not in ENV_TO_FLAG, (
            f"{internal} 是框架运行期自设的，不该暴露成 CLI 参数（会误导用户去改它）"
        )


def test_no_duplicate_flag_semantics():
    """同一个环境变量不许映射到两个 CLI 参数（项目铁律：同一能力收敛成唯一入口）。"""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.cli import ENV_TO_FLAG

    flags = list(ENV_TO_FLAG.values())
    dupes = {f for f in flags if flags.count(f) > 1}
    assert not dupes, f"这些 CLI 参数被多个环境变量映射（入口不唯一）：{dupes}"
