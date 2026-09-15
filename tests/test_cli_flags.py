"""CLI 参数契约的回归测试（2026-09-13 新增）。

保护一条约定：**未知 / 错位参数一律报错 + 非 0 退出，绝不静默忽略**
（起因：`--workres` 拼错被静默忽略、未知子命令 exit 0）。

跑法：
    cd ~/hybrid_gui_qa && source .venv/bin/activate
    python -m pytest tests/test_cli_flags.py -q
（不需要被测 demo、不需要 DeepSeek key：全部只走参数校验，不真跑浏览器）
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from framework.cli import CMD_FLAGS, FLAG_SPECS, _validate_args
from framework.text_io import utf8_env


def _cli(*args: str) -> subprocess.CompletedProcess:
    """跑真实 CLI（只测参数层：命中错误会在开浏览器之前就退出）。

    显式 UTF-8 解码 + 给子进程注入 UTF-8 口径：父进程绝不按系统默认编码
    （Windows cp936/gbk）解码子进程的 UTF-8 中文输出（2026-09-13 gbk 事故同源）。
    """
    return subprocess.run([sys.executable, "-m", "framework.cli", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=utf8_env(), timeout=60)


# ---------- 一、合法参数必须全部通过（防误杀现有用法）----------
LEGAL = [
    ("probe", []),
    ("generate", []),
    ("generate", ["--live-probe"]),
    ("generate", ["--element-map", "output/element_maps/element_map_x.json"]),
    ("generate", ["--allow-unmapped"]),
    ("all", ["--workers", "1", "--allow-unmapped"]),
    ("run", []),
    ("run", ["--workers", "2"]),
    ("run", ["--debug"]),
    ("run", ["--debug", "false"]),
    ("run", ["--debug", "true", "--slowmo", "500"]),
    ("run", ["--headed"]),
    ("run", ["--force-workers", "--case", "hand_enter_search"]),
    ("run", ["--case", "a", "--case", "b"]),
    ("all", ["--workers", "1", "--debug"]),
    ("prune", ["--dry-run"]),
    ("prune", ["--keep", "20"]),
    ("explore", ["--ai", "--scenario", "在搜索框输入合同1并点搜索"]),
    ("explore", ["--ai", "--scenario-file", "scenarios/contracts/x.yml"]),
    ("explore", ["--ai", "--scenario-dir", "scenarios/", "--tag", "smoke",
                 "--limit", "2", "--no-verify"]),
    ("explore", ["--ai", "--scenario", "x", "--no-cases", "--verify"]),
]


@pytest.mark.parametrize("cmd,rest", LEGAL, ids=[f"{c} {' '.join(r)}" for c, r in LEGAL])
def test_legal_args_pass(cmd, rest):
    _validate_args(cmd, rest)          # 不抛异常 = 通过


# ---------- 二、非法参数必须报错退出 2 ----------
ILLEGAL = [
    # (参数, 期望报错关键词, 期望给出建议)
    (["prune", "--dry-run", "--workres", "1"], "不认识的参数", "--workers"),
    (["run", "--head"], "不认识的参数", "--headed"),
    (["run", "--worker", "2"], "不认识的参数", "--workers"),
    (["frobnicate"], "未知子命令", "是不是想写"),
    (["explore", "--ai", "--scenario", "x", "--to-cases"], "已移除", "--no-cases"),
    (["probe", "--workers", "2"], "对 probe 无效", "run"),
    (["prune", "--ai"], "对 prune 无效", "explore"),
    (["run", "--workers"], "缺少取值", "--workers <值>"),
    (["run", "--case"], "缺少取值", "--case <值>"),
    (["probe", "extra-positional"], "多余的位置参数", "不接受位置参数"),
]


@pytest.mark.parametrize("args,keyword,hint", ILLEGAL,
                         ids=[" ".join(a) for a, _, _ in ILLEGAL])
def test_illegal_args_fail_loud(args, keyword, hint):
    r = _cli(*args)
    err = r.stdout + r.stderr
    assert r.returncode == 2, f"期望 exit 2，实际 {r.returncode}\n{err}"
    assert keyword in err, f"报错信息里应含 {keyword!r}\n{err}"
    assert hint in err, f"应给出提示 {hint!r}\n{err}"


def test_explore_without_ai_is_not_silent():
    """explore 缺 --ai：过去静默 return（exit 0），现在必须报错。"""
    r = _cli("explore", "--scenario", "在搜索框输入合同1")
    assert r.returncode == 2
    assert "--ai" in (r.stdout + r.stderr)


# ---------- 三、帮助 / 版本 ----------
def test_help_overview_lists_all_commands():
    r = _cli("--help")
    assert r.returncode == 0
    for c in CMD_FLAGS:
        assert c in r.stdout


@pytest.mark.parametrize("cmd", sorted(CMD_FLAGS))
def test_subcommand_help(cmd):
    r = _cli(cmd, "--help")
    assert r.returncode == 0
    assert cmd in r.stdout


def test_version_matches_build_html_single_source():
    """--version 必须和 build_html.py（版本单一来源）一致，不允许两处各写。"""
    import re
    from pathlib import Path
    r = _cli("--version")
    assert r.returncode == 0
    src = (Path(__file__).resolve().parents[1] / "build_html.py").read_text(encoding="utf-8")
    v = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M).group(1)
    d = re.search(r'^VERSION_DATE\s*=\s*"([^"]+)"', src, re.M).group(1)
    assert f"v{v} ({d})" in r.stdout


# ---------- 四、契约自检：不许留重复定义 ----------
def test_arg_values_defined_once():
    from framework import cli
    src = (cli.__file__)
    text = open(src, encoding="utf-8").read()
    assert text.count("def _arg_values(") == 1, "CLI 里 _arg_values 又出现重复定义了"


def test_flag_specs_and_cmd_flags_consistent():
    """CMD_FLAGS 里引用的 flag 必须在 FLAG_SPECS 里有定义（防两处漂移）。"""
    for cmd, flags in CMD_FLAGS.items():
        for f in flags:
            assert f in FLAG_SPECS, f"{cmd} 声明了未定义的参数 {f}"
